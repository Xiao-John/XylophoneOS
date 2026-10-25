# SPDX-License-Identifier: Apache-2.0
"""Compile and run UNICODE_example1.cpp with the native XOS G++ toolchain."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]
from e08_storage_smoke import boot
from gcc_seed_smoke import (guest_tool, import_manifest_files, read_manifest,
                            validate_bundle)
from make_work_disk import create_fat32
from task_smoke import pump, send_bytes
from work_disk import transfer

SOURCE = ROOT / "tests/fixtures/utf8/UNICODE_example1.cpp"
EXPECTED = ("Wir müssen wissen, Wir werden wissen.\n"
            "我们必须知道，我们终将知道。\n").encode()


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def run(guest, line, timeout=240):
    start = len(guest.output)
    send_bytes(guest, line.encode() + b"\r")
    guest.expect(b"kind=exited code=", start=start, timeout=timeout)
    exited = guest.output.find(b"kind=exited code=", start)
    guest.expect_any((b"xsh> ", b"sup> "), start=exited, timeout=30)
    pump(guest, 0.3)
    return bytes(guest.output[start:])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-manifest", type=Path,
                        default=ROOT / "build/cpp_bundle/seed_manifest.json")
    parser.add_argument("--seed-root", type=Path, default=ROOT)
    parser.add_argument("--sysroot-manifest", type=Path,
                        default=ROOT / "build/cpp_bundle/sysroot_manifest.json")
    parser.add_argument("--sysroot-root", type=Path, default=ROOT)
    parser.add_argument("--report", type=Path,
                        default=ROOT / "build/utf8_example1_native_report.json")
    args = parser.parse_args()

    seed_path, seed = read_manifest(args.seed_manifest.resolve(),
                                    ("gcc", "g++", "cc1", "cc1plus", "as", "ld"))
    pre = validate_bundle(args.seed_manifest.resolve(), args.seed_root.resolve(),
                          args.sysroot_manifest.resolve(), args.sysroot_root.resolve(),
                          "/sysroot", ("gcc", "g++", "cc1", "cc1plus", "as", "ld"))
    if not pre.ok:
        raise SystemExit("native bundle preflight failed: " + pre.summary)
    system = json.loads((ROOT / "build/manifest.json").read_text())
    report = {
        "gate": "U0/U1 native UTF-8 example",
        "build_id": system["build_id"],
        "xos_image_sha256": sha256(ROOT / "build/xos.img"),
        "seed_manifest_sha256": sha256(seed_path),
        "source_sha256": sha256(SOURCE),
        "expected_sha256": hashlib.sha256(EXPECTED).hexdigest(),
        "compile_command": None,
        "checks": [],
        "status": "failed",
    }
    with tempfile.TemporaryDirectory(prefix="xos_utf8_native_") as folder:
        tmp = Path(folder)
        disk = tmp / "utf8.img"
        create_fat32(disk, 2048)
        for path in ("/src", "/out", "/tmp"):
            transfer(disk, "mkdir", path)
        transfer(disk, "import", "/src/UNICODE_example1.cpp", SOURCE)
        report["seed_files"] = len(import_manifest_files(
            disk, args.seed_root, seed["install_files"], "Seed"))
        sysroot = json.loads(args.sysroot_manifest.read_text())
        report["sysroot_files"] = len(import_manifest_files(
            disk, args.sysroot_root, sysroot["files"], "sysroot"))

        guest = boot(disk, "utf8_example1_native")
        try:
            gxx = guest_tool(seed, "g++")
            compile_line = (f"{gxx} -static --sysroot=/sysroot "
                            f"-o /out/UNICODE_example1 /src/UNICODE_example1.cpp")
            report["compile_command"] = compile_line
            compile_output = run(guest, compile_line)
            compile_ok = b"kind=exited code=0" in compile_output and b"error:" not in compile_output
            report["checks"].append({"name": "compile", "passed": compile_ok,
                                     "tail": compile_output[-600:].decode("utf-8", "replace")})
            if compile_ok:
                program_output = run(guest, "/out/UNICODE_example1")
                position = program_output.find(EXPECTED)
                exact = position >= 0 and program_output[position:position + len(EXPECTED)] == EXPECTED
                exited = b"kind=exited code=0" in program_output
                report["checks"].append({
                    "name": "run", "passed": exact and exited,
                    "found_expected": position >= 0, "exit_zero": exited,
                    "observed_sha256": hashlib.sha256(program_output).hexdigest(),
                })
        finally:
            guest.close()
    report["status"] = "passed" if all(c["passed"] for c in report["checks"]) else "failed"
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
