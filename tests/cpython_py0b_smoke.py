# SPDX-License-Identifier: Apache-2.0
"""PY0b: boot the cross-built CPython and run real scripts on XOS."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]
from boot_smoke import Guest
from make_work_disk import create_fat32
from task_smoke import pump, send_bytes
from work_disk import transfer

SKIP_PARTS = {"test", "idlelib", "tkinter", "turtledemo", "ensurepip",
              "lib2to3", "__pycache__", "site-packages"}
GUEST_LIB = "/usr/lib/python3.14"
SUFFIXES = {".py", ".pyi", ".txt", ".cfg", ".json"}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def latest_work():
    reports = sorted(
        (path.parent for path in (ROOT / ".cache/xos_seed/cpython").glob("*/py0a_report.json")),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for work in reports:
        report = json.loads((work / "py0a_report.json").read_text())
        if report.get("status") == "built_not_run":
            return work, report
    raise SystemExit("no completed PY0a build found; run build_cpython.py --compile-probe")


def install_lib(disk, lib):
    created = {"/usr", "/usr/bin", "/usr/lib", GUEST_LIB, "/tmp"}
    count = 0
    for path in sorted(lib.rglob("*")):
        rel = path.relative_to(lib)
        if any(part in SKIP_PARTS for part in rel.parts):
            continue
        guest = f"{GUEST_LIB}/{rel.as_posix()}"
        if path.is_dir():
            if guest not in created:
                transfer(disk, "mkdir", guest)
                created.add(guest)
            continue
        if path.suffix not in SUFFIXES:
            continue
        parent = guest.rsplit("/", 1)[0]
        if parent not in created:
            transfer(disk, "mkdir", parent)
            created.add(parent)
        transfer(disk, "import", guest, path)
        count += 1
    return count


ANSI = __import__("re").compile(r"\x1b\[[0-9;]*m")


def run(guest, command, timeout=120):
    start = len(guest.output)
    send_bytes(guest, command.encode() + b"\r")
    guest.expect(b"kind=exited code=", start=start, timeout=timeout)
    exited = guest.output.find(b"kind=exited code=", start)
    guest.expect(b"sup> ", start=exited, timeout=30)
    pump(guest, 0.2)
    text = bytes(guest.output[start:]).decode("utf-8", "replace")
    return ANSI.sub("", text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path)
    parser.add_argument("--image", type=Path, default=ROOT / "build/xos.img")
    args = parser.parse_args()
    work, build_report = (args.work, None) if args.work else latest_work()
    if build_report is None:
        build_report = json.loads((work / "py0a_report.json").read_text())
    interpreter = work / "target_build/python.exe"
    lib = work / "source/Lib"
    manifest = json.loads((ROOT / "build/manifest.json").read_text())
    report = {
        "build_id": manifest["build_id"],
        "xos_image_sha256": sha256(args.image),
        "py0a": {key: build_report.get(key) for key in
                  ("fingerprint", "version", "status", "sdk_build_id", "sdk_path")},
        "checks": [],
        "status": "failed",
    }
    with tempfile.TemporaryDirectory(prefix="xos_cpython_") as folder:
        base = Path(folder)
        stripped = base / "python3"
        subprocess.run(["x86_64-elf-strip", "-o", str(stripped), str(interpreter)], check=True)
        report["interpreter"] = {
            "unstripped_sha256": sha256(interpreter),
            "stripped_sha256": sha256(stripped),
            "stripped_bytes": stripped.stat().st_size,
        }
        disk = base / "work.img"
        create_fat32(disk, 2048)
        for path in ("/usr", "/usr/bin", "/usr/lib", GUEST_LIB, "/tmp"):
            transfer(disk, "mkdir", path)
        transfer(disk, "import", "/usr/bin/python3", stripped)
        report["stdlib_files"] = install_lib(disk, lib)

        samples = {
            "hello.py": 'print("hello from xos python")\n',
            "unicode.py": 'print(ord(chr(233)), len("h\\u00e9llo"))\n',
            "error.py": 'raise ValueError("py0b marker")\n',
            "gc.py": 'import gc; gc.collect(); print(gc.isenabled())\n',
            "helper.py": 'VALUE = 41\n',
            "imports.py": 'import helper; print(helper.VALUE + 1)\n',
        }
        for name, text in samples.items():
            source = base / name
            source.write_text(text)
            transfer(disk, "import", f"/tmp/{name}", source)

        guest = Guest(args.image, "cpython_py0b", work_disk=disk)
        try:
            guest.expect(b"xos64> ", timeout=30)
            start = len(guest.output)
            send_bytes(guest, b"run\r")
            guest.expect_supervisor(start=start, timeout=40)
            pump(guest, 1.0)

            def check(name, command, expected, code="0", absent=None):
                text = run(guest, command)
                ok = expected in text and f"kind=exited code={code}" in text
                if absent is not None and absent in text:
                    ok = False
                report["checks"].append({
                    "name": name, "command": command, "expected": expected,
                    "exit": code, "passed": ok,
                    "tail": text[-500:],
                })
                return ok

            results = [
                check("arithmetic", "python3 -c print(2+2)", "\n4\n"),
                check("script", "python3 /tmp/hello.py", "hello from xos python"),
                check("unicode", "python3 /tmp/unicode.py", "233 5"),
                check("exception", "python3 /tmp/error.py", "ValueError: py0b marker", code="1"),
                check("gc", "python3 /tmp/gc.py", "True"),
                check("import", "python3 /tmp/imports.py", "42"),
                check("repeat-init", "python3 -c print(2+2)", "\n4\n"),
            ]
            report["status"] = "passed" if all(results) else "failed"
        finally:
            guest.close()
    (ROOT / "build/cpython_py0b_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
