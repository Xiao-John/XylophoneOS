# SPDX-License-Identifier: Apache-2.0
"""Exercise GNU Make and its child lifecycle on a disposable XOS disk."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]
from boot_smoke import Guest
from cpython_py0b_smoke import run
from make_work_disk import create_fat32
from process_smoke import resources
from task_smoke import send_bytes
from work_disk import transfer
from xypm_format import canonical, load_json, require, sha_file


FIXTURES = ROOT / "tests/fixtures/gnu_make"
MAKE = "gmake -B -r -f /work/Makefile"
CASES = (
    ("version", "gmake --version", 0, "GNU Make 4.4.1"),
    ("variables_dependencies", MAKE + " WORD=override all", 0, "GNU_MAKE_DEPS_OK override"),
    ("wildcard", MAKE + " wildcard", 0, "GNU_MAKE_WILDCARD </work/vars.mk>"),
    ("local_parallel_wait", MAKE + " -j2 concurrent", 0, "GNU_MAKE_PARALLEL_OK"),
    ("pipe_recipe", MAKE + " pipe", 0, "GNU_MAKE_PIPE_OK"),
    ("capture_pipe", MAKE + " capture", 0, "GNU_MAKE_CAPTURE <real-pipe-data>"),
    ("parallel_error", MAKE + " -j2 -k broken survivor", 2, "GNU_MAKE_SURVIVOR_OK\nError 7"),
    ("closed_partial_output", "/usr/bin/mkprobe absent /out/incomplete", 0, ""),
    ("after_error", "dash /work/recovery.sh", 0, "GNU_MAKE_DASH_OK"),
    ("reject_jobserver", MAKE + " --jobserver-style=pipe all", 2, "recursive jobserver is unavailable"),
    ("reject_makefile_jobserver", MAKE + " -j2 late_jobserver", 2, "recursive jobserver is unavailable"),
    ("no_jobserver_recipe", "/usr/bin/mkprobe absent /out/unexpected_jobserver", 0, ""),
    ("reject_output_sync", MAKE + " --output-sync=target all", 2, "output synchronization is unavailable"),
)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ("image", "system-manifest", "make-manifest", "profile", "dash-manifest", "probe", "output-dir"):
        cli.add_argument("--" + name, required=True, type=Path)
    args = cli.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    system = load_json(args.system_manifest)
    tool = load_json(args.make_manifest)
    dash_build = load_json(args.dash_manifest)
    dash = ROOT / dash_build["elf"]
    probe = load_json(args.probe.with_name(args.probe.name + ".build") / "manifest.json")
    canonical_profile = hashlib.sha256(canonical(load_json(args.profile))).hexdigest()
    binary = args.make_manifest.parent / tool["elf"]["path"]
    require(sha_file(args.image) == system["artifacts"]["xos-install.iso"]["sha256"],
            "ordinary ISO differs from the system manifest")
    require(sha_file(binary) == tool["elf"]["sha256"] and sha_file(args.profile) == tool["profile_sha256"],
            "GNU Make ELF or profile differs from the build")
    require(dash_build["profile"] == "dash_glibc_preview" and sha_file(dash) == dash_build["sha256"]
            and dash_build["inputs"]["profile"] == canonical_profile
            and dash_build["inputs"]["sdk/manifest.json"] == tool["sdk_manifest_sha256"],
            "dash differs from the same glibc build profile")
    require(sha_file(args.probe) == probe["elf_sha256"] and len(probe["sources"]) == 1
            and sha_file(FIXTURES / "probe.c") in probe["sources"].values()
            and probe["profile_binding"]["profile_sha256"] == canonical_profile
            and probe["sdk_manifest_sha256"] == tool["sdk_manifest_sha256"],
            "fixture ELF differs from its source or the same glibc profile")
    report = {"status": "failed", "build_id": system["build_id"], "image_sha256": sha_file(args.image),
              "make_sha256": sha_file(binary), "sdk_manifest_sha256": tool["sdk_manifest_sha256"],
              "profile_sha256": sha_file(args.profile), "dash_sha256": sha_file(dash),
              "probe_sha256": sha_file(args.probe), "runner_sha256": sha_file(Path(__file__)), "cases": []}
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix="gnu_make_work_") as lab:
            folder = Path(lab)
            disk = folder / "disk.img"
            create_fat32(disk, 512)
            for path in ("/usr", "/usr/bin", "/work", "/out"):
                transfer(disk, "mkdir", path)
            recovery = folder / "recovery.sh"
            recovery.write_text("set -e\n" + MAKE + " survivor\necho GNU_MAKE_DASH_OK\n")
            payloads = (("/usr/bin/gmake", binary), ("/usr/bin/dash", dash),
                        ("/usr/bin/mkprobe", args.probe), ("/work/Makefile", FIXTURES / "Makefile"),
                        ("/work/vars.mk", FIXTURES / "vars.mk"), ("/work/recovery.sh", recovery))
            for name, path in payloads:
                transfer(disk, "import", name, path)
            report["inputs"] = {name: sha_file(path) for name, path in payloads}
            guest = Guest(args.image, "gnu_make_guest", work_disk=disk, log_dir=args.output_dir)
            report["qemu"] = subprocess.check_output([guest.command[0], "--version"], text=True).splitlines()[0]
            guest.expect(b"xos64> ", timeout=45)
            start = len(guest.output)
            send_bytes(guest, b"run\r")
            guest.expect_supervisor(trace=True, start=start, timeout=45)
            start = len(guest.output)
            send_bytes(guest, b"demo quiet\r")
            guest.expect_supervisor(start=start, timeout=30)
            baseline = resources(guest)
            for name, command, status, marker in CASES:
                print(name, flush=True)
                output = run(guest, command, timeout=60)
                report["cases"].append({"name": name, "expected_status": status, "output": output})
                require(all(part in output for part in marker.splitlines())
                        and "kind=exited code=" + str(status) + "\n" in output,
                        name + " returned the wrong output or exit status")
                require(resources(guest) == baseline, name + " did not restore the guest resource baseline")
            start = len(guest.output)
            send_bytes(guest, b"sync\r")
            guest.expect(b"[files] sync=ok", start=start, timeout=30)
            guest.close()
            for name in ("common", "first", "second"):
                out = args.output_dir / name
                transfer(disk, "export", "/out/" + name, out)
                require(out.read_bytes() == b"ran\n", name + " must execute once")
            report.update(status="passed_subset", resources=baseline)
    finally:
        if guest:
            guest.close()
            (args.output_dir / "serial.log").write_bytes(guest.output)
        (args.output_dir / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
