#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check discovery and render a glyph with the locked XOS WebCore font inputs."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
PORT = ROOT / "src/ports/webkit"
sys.path.insert(0, str(ROOT / "scripts"))
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import pump, send_bytes
from work_disk import transfer


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def discover(archive, target, output):
    lock_path = PORT / "source_lock.json"
    lock = json.loads(lock_path.read_bytes())
    if digest(archive) != lock["sha256"]:
        raise ValueError("WebKit archive differs from the source lock")
    modules = output / "modules"
    modules.mkdir()
    name = "FindHarfBuzz.cmake"
    with tarfile.open(archive, "r:xz") as source:
        member = source.getmember(lock["archive_root"] + "/Source/cmake/" + name)
        if not member.isfile():
            raise ValueError("the locked CMake module is not a regular file")
        with source.extractfile(member) as stream:
            (modules / name).write_bytes(stream.read())
    fixture = ROOT / "tests/fixtures/webkit/font_packages"
    cmake_build = output / "cmake"
    with (output / "discovery.log").open("w") as log:
        subprocess.run(["cmake", "-S", fixture, "-B", cmake_build,
                        f"-DXOS_FONT_PREFIX={target / 'prefix'}", f"-DXOS_WEBKIT_MODULES={modules}"],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    freetype, harfbuzz = (cmake_build / "target-versions.txt").read_text().splitlines()
    return {"webkit_archive_sha256": lock["sha256"], "webkit_find_module_sha256": digest(modules / name),
            "fixture_sha256": digest(fixture / "CMakeLists.txt"), "freetype_version": freetype,
            "harfbuzz_version": harfbuzz,
            "cmake_version": subprocess.check_output(["cmake", "--version"], text=True).splitlines()[0]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("webkit-archive", "target", "system", "dash", "dash-receipt", "output"):
        parser.add_argument("--" + name, required=True, type=lambda value: Path(value).resolve())
    parser.add_argument("--dash-timeout", type=int, default=420,
                        help="per-invocation guest deadline for the large static ICU ELF, in seconds")
    args = parser.parse_args()
    if args.dash_timeout <= 0:
        parser.error("--dash-timeout must be positive")
    args.output.mkdir(parents=True, exist_ok=False)
    image = args.system / "xos-install.iso"
    system_receipt = args.system / "manifest.json"
    target_receipt = args.target / "manifest.json"
    system = json.loads(system_receipt.read_bytes())
    target = json.loads(target_receipt.read_bytes())
    dash = json.loads(args.dash_receipt.read_bytes())
    if digest(image) != system["artifacts"][image.name]["sha256"]:
        raise ValueError("system ISO digest mismatch")
    if target["status"] != "target_font_stack_linked":
        raise ValueError("the font-stack build receipt has not reached the static link")
    if digest(args.dash) != dash["sha256"]:
        raise ValueError("dash ELF differs from its receipt")
    for name, expected in target["artifacts"].items():
        if digest(args.target / name) != expected:
            raise ValueError(f"target font artifact mismatch: {name}")
    result = {"status": "failed", "build_id": system["build_id"], "iso_sha256": digest(image),
              "system_manifest_sha256": digest(system_receipt), "target_manifest_sha256": digest(target_receipt),
              "probe_sha256": target["artifacts"]["font_stack.elf"],
              "sample_sha256": target["artifacts"]["sample.ttf"], "runner_sha256": digest(Path(__file__)),
              "dash_sha256": dash["sha256"], "dash_receipt_sha256": digest(args.dash_receipt)}
    guest = None
    try:
        result["discovery"] = discover(args.webkit_archive, args.target, args.output)
        with tempfile.TemporaryDirectory(prefix="xos_webkit_fonts_") as directory:
            disk = Path(directory) / "work.img"
            create_fat32(disk, 512)
            transfer(disk, "mkdir", "/fonts")
            transfer(disk, "import", "/fonts/probe.elf", args.target / "font_stack.elf")
            transfer(disk, "import", "/fonts/sample.ttf", args.target / "sample.ttf")
            transfer(disk, "mkdir", "/usr")
            transfer(disk, "mkdir", "/usr/bin")
            transfer(disk, "import", "/usr/bin/dash", args.dash)
            script = Path(directory) / "font.sh"
            script.write_text('/fonts/probe.elf "$1"\n')
            transfer(disk, "import", "/fonts/run.sh", script)
            guest = Guest(image, "webkit_fonts", work_disk=disk, log_dir=args.output)
            result["qemu_version"] = subprocess.check_output([guest.command[0], "--version"], text=True).splitlines()[0]
            guest.expect(b"xos64> ", timeout=30)
            send_bytes(guest, b"run\r")
            guest.expect_supervisor(trace=True, timeout=30)
            command(guest, "demo quiet", b"demo tasks")
            pump(guest, 1)
            result["resources_before"] = resources(guest)
            result["entries"] = {}
            exit_line = rb"\[wait\] pid=\d+ kind=exited code=(\d+)"
            glyph_line = rb"WEBKIT_FONT_STACK_PASS icu=3 ligature=(\d+) bitmap=(\d+)x(\d+) ink=(\d+)"
            for shell, launch in (("xsh", "exec-file /fonts/probe.elf"), ("dash", "dash /fonts/run.sh")):
                limit = args.dash_timeout if shell == "dash" else 120
                began = time.monotonic()
                missing = command(guest, launch + " /fonts/missing.ttf", b"kind=", timeout=limit)
                missing_seconds = round(time.monotonic() - began, 3)
                if re.findall(exit_line, missing) != [b"2"]:
                    raise AssertionError(missing[-5000:])
                if resources(guest) != result["resources_before"]:
                    raise AssertionError(f"an unreadable font changed the resource baseline under {shell}")
                began = time.monotonic()
                output = command(guest, launch + " /fonts/sample.ttf", b"kind=", timeout=limit)
                glyph_seconds = round(time.monotonic() - began, 3)
                evidence = re.findall(glyph_line, output)
                if len(evidence) != 1 or not all(int(value) > 0 for value in evidence[0]):
                    raise AssertionError(output[-5000:])
                if re.findall(exit_line, output) != [b"0"]:
                    raise AssertionError(output[-5000:])
                remaining = resources(guest)
                if remaining != result["resources_before"]:
                    raise AssertionError(f"font stack changed the resource baseline under {shell}")
                result["entries"][shell] = {"missing_sample_exit": 2, "resources_after": remaining,
                    "missing_seconds": missing_seconds, "glyph_seconds": glyph_seconds,
                    "deadline_seconds": limit,
                    "glyph": dict(zip(("index", "width", "height", "ink"), map(int, evidence[0])))}
            result["status"] = "passed_subset"
    finally:
        if guest:
            guest.close()
            (args.output / "guest.serial.log").write_bytes(guest.output)
        (args.output / "report.json").write_text(json.dumps(result, indent=2) + "\n")
    print(result["status"])


if __name__ == "__main__":
    main()
