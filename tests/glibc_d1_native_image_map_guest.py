#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Map one ordinary GCC PIC ELF from an authenticated native file pin."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from boot_smoke import Guest
from build_glibc_program import verify_elf
from glibc_d1_layout_guest import BIASES, fixture_layout
from glibc_g1_probe import clean_build_environment
from make_work_disk import create_fat32
from process_smoke import command, resources
from shell_launch_support import bind_system, check_result, sha, write_report
from task_smoke import send_bytes
from toolchain import COMMON_FLAGS, X86_FLAGS, audit, tool
from work_disk import transfer


FIXTURES = ROOT / "tests/fixtures/glibc_d1"


def make_plan(dso, path, layout):
    with path.open("x") as stream:
        stream.write(f"static constexpr xos::u32 file_bytes = {dso.stat().st_size};\n")
        stream.write("static constexpr xos::u8 wanted_digest[32] = {"
                     + ", ".join(hex(value) for value in bytes.fromhex(sha(dso))) + "};\n")
        stream.write("static constexpr xos::elf::segment loads[] = {\n")
        for offset, address, file_bytes, memory_bytes, _, _, permissions in layout["loads"]:
            values = (offset, address, file_bytes, memory_bytes, permissions)
            stream.write("    {" + ", ".join(hex(value) for value in values) + "},\n")
        stream.write("};\n")
        for name, value in layout.items():
            if name not in ("loads", "hole_offset"):
                stream.write(f"static constexpr xos::u64 {name} = {value:#x};\n")


def build_assets(system, output, report):
    sdk = system / "sdk"
    tools = {name: str(Path(tool(name)).resolve(strict=True))
             for name in ("gcc", "g++", "as", "ld", "readelf")}
    report["tools"] = {name: {"path": path, "sha256": sha(path)} for name, path in tools.items()}
    env, removed = clean_build_environment(os.environ)
    env["LC_ALL"] = "C"
    report["sanitized_environment"] = removed
    tool_prefix = "-B" + str(system / "target_tools") + "/"
    assert sha(system / "target_tools/as") == report["tools"]["as"]["sha256"]
    assert sha(system / "target_tools/ld") == report["tools"]["ld"]["sha256"]
    compiler_headers = subprocess.check_output([tools["gcc"], "-print-file-name=include"],
                                               text=True, env=env).strip()
    pic, dso, header, obj, bootstrap = (output / name for name in
                                      ("layout.o", "layout.so", "native_image_plan.hpp",
                                       "bootstrap.o", "bootstrap.elf"))
    commands = report["commands"] = {}

    def run(name, arguments):
        argv = list(map(str, arguments))
        commands[name] = argv
        with (output / f"{name}.log").open("w") as log:
            subprocess.run(argv, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)

    run("compile_pic", [tools["gcc"], tool_prefix, "-nostdinc", "-isystem", sdk / "include",
                        "-isystem", compiler_headers, "-std=gnu11", "-O2", "-ffreestanding",
                        "-fPIC", "-mcmodel=small", "-mno-red-zone", "-fno-stack-protector",
                        "-fno-asynchronous-unwind-tables", "-fno-unwind-tables", "-fvisibility=hidden",
                        "-c", FIXTURES / "layout_dso.c", "-o", pic])
    run("link_pic", [tools["ld"], "-shared", "-e", "d1_entry", "-z", "relro", "-z", "now",
                     "-z", "noexecstack", "-z", "max-page-size=8192", "-z", "separate-code",
                     "--build-id=none", "--no-undefined", "--hash-style=gnu", "-o", dso, pic])
    run("inspect_pic", [tools["readelf"], "-hW", "-lW", "-rW", "-dW", dso])
    layout = fixture_layout(dso.read_bytes())
    make_plan(dso, header, layout)
    run("compile_bootstrap", [tools["g++"], tool_prefix, *COMMON_FLAGS, *X86_FLAGS,
                              "-I", sdk / "include", "-I", ROOT / "src/user/loader", "-I", output,
                              "-c", FIXTURES / "native_image_map_guest.cpp", "-o", obj])
    run("link_bootstrap", [tools["ld"], "-z", "noexecstack", "-z", "max-page-size=4096",
                           "--build-id=none", "--no-undefined", "-T", sdk / "user.ld",
                           sdk / "crt0.o", obj, "--start-group", sdk / "lib/libxos_loader.a",
                           sdk / "lib/libxos.a", "--end-group", "-o", bootstrap])
    verify_elf(bootstrap)
    assert dso.read_bytes() not in bootstrap.read_bytes()
    report["layout"] = layout
    report["inputs"] = {"loader_archive_sha256": sha(sdk / "lib/libxos_loader.a"),
                        "artifacts": {path.name: sha(path) for path in (pic, dso, header, obj, bootstrap)}}
    return dso, bootstrap


def exercise(image, output, dso, bootstrap, report):
    with tempfile.TemporaryDirectory(prefix="d1_native_map_") as folder:
        disk = Path(folder) / "work.img"
        create_fat32(disk, 512)
        transfer(disk, "mkdir", "/bin")
        transfer(disk, "import", "/bin/layout.so", dso)
        transfer(disk, "import", "/bin/d1_native_map", bootstrap)
        guest = Guest(image, "d1_native_map", work_disk=disk, qmp_enabled=False, log_dir=output)
        try:
            report["qemu_command"] = guest.command
            report["qemu_version"] = subprocess.check_output([guest.command[0], "--version"],
                                                             text=True).splitlines()[0]
            guest.expect(b"xos64> ", timeout=40)
            send_bytes(guest, b"run\r")
            guest.expect_supervisor(trace=True, timeout=40)
            command(guest, "demo quiet", b"demo tasks")
            report["resources_before"] = resources(guest)
            denied = command(guest, "exec-file /bin/layout.so", b"incompatible target or format")
            assert b"format=target" in denied and b"[loader] started" not in denied
            assert resources(guest) == report["resources_before"]
            report["static_entry_rejected_et_dyn"] = True
            result = command(guest, "exec-file /bin/d1_native_map", b"kind=", timeout=90)
            report["output"] = result.decode(errors="replace")
            expected = tuple(f"D1_NATIVE_MAP {bias} 17551 19597".encode() for bias in BIASES)
            check_result(result, 0, (*expected, b"D1_NATIVE_MAP_OK pin=verified offset=preserved bss=zero rollback=complete"))
            report["resources_after"] = resources(guest)
            assert report["resources_before"] == report["resources_after"]
        finally:
            guest.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    system, output = args.system.resolve(strict=True), args.output.resolve()
    manifest = bind_system(system)
    assert audit() == manifest["tools"]
    output.mkdir(parents=True, exist_ok=False)
    report = {"status": "failed", "scope": "native pinned LOAD mapping for a verified fixture",
              "build_id": manifest["build_id"], "system_manifest_sha256": sha(system / "manifest.json"),
              "system_iso_sha256": manifest["artifacts"]["xos-install.iso"]["sha256"]}
    try:
        dso, bootstrap = build_assets(system, output, report)
        exercise(system / "xos-install.iso", output, dso, bootstrap, report)
        assert bind_system(system) == manifest
        for info in report["tools"].values():
            assert sha(info["path"]) == info["sha256"]
        for name, digest in report["inputs"]["artifacts"].items():
            assert sha(output / name) == digest
        report["status"] = "passed_subset"
    finally:
        write_report(output / "report.json", report)
    print(report["status"])


if __name__ == "__main__":
    main()
