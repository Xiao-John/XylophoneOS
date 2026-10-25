# SPDX-License-Identifier: Apache-2.0
"""PY1: verify scripts, argv/cwd/env, imports and selected stdlib on XOS."""

import argparse
import json
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]
from boot_smoke import Guest
from cpython_py0b_smoke import run
from make_work_disk import create_fat32
from stage_cpython import accepted_work, sha256, stage_cpython
from task_smoke import pump, send_bytes
from work_disk import transfer


FIXTURES = ROOT / "tests/fixtures/cpython_py1"


def install_stage(disk, stage):
    directories = sorted(
        (path for path in stage.rglob("*") if path.is_dir()),
        key=lambda path: (len(path.relative_to(stage).parts), str(path)),
    )
    for path in directories:
        transfer(disk, "mkdir", "/" + path.relative_to(stage).as_posix())
    for path in sorted(stage.rglob("*")):
        if path.is_file():
            transfer(disk, "import", "/" + path.relative_to(stage).as_posix(), path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path)
    parser.add_argument("--image", type=Path, default=ROOT / "build/xos.img")
    args = parser.parse_args()
    work = (args.work or accepted_work()).resolve(strict=True)
    stage, stage_manifest = stage_cpython(work)
    system_manifest = json.loads((ROOT / "build/manifest.json").read_text())
    report = {
        "phase": "PY1",
        "build_id": system_manifest["build_id"],
        "xos_image_sha256": sha256(args.image),
        "cpython_fingerprint": stage_manifest["fingerprint"],
        "stage_manifest_sha256": sha256(work / "stage_py1_manifest.json"),
        "stage_file_count": stage_manifest["file_count"],
        "checks": [],
        "status": "failed",
    }

    with tempfile.TemporaryDirectory(prefix="xos_cpython_py1_") as folder:
        temporary = Path(folder)
        disk = temporary / "work.img"
        create_fat32(disk, 2048)
        install_stage(disk, stage)
        for guest_path in ("/work", "/work/py1"):
            transfer(disk, "mkdir", guest_path)
        for fixture in sorted(FIXTURES.glob("*.py")):
            transfer(disk, "import", f"/work/py1/{fixture.name}", fixture)
        payload = temporary / "payload.dat"
        payload.write_bytes(b"\x00X\n\x7f\xff")
        transfer(disk, "import", "/work/py1/payload.dat", payload)
        byte_probe = temporary / "byte_probe.py"
        byte_probe.write_text(
            'data=open("/work/py1/payload.dat","rb").read();'
            'print("PY1_BYTES",len(data),data.hex())\n'
        )
        transfer(disk, "import", "/work/py1/byte_probe.py", byte_probe)

        guest = Guest(args.image, "cpython_py1", work_disk=disk)
        try:
            guest.expect(b"xos64> ", timeout=30)
            start = len(guest.output)
            send_bytes(guest, b"run\r")
            guest.expect_supervisor(trace=True, start=start, timeout=40)
            pump(guest, 1.0)

            def check(name, command, expected, code="0", absent=None):
                text = run(guest, command, timeout=180)
                passed = expected in text and f"kind=exited code={code}" in text
                if absent is not None and absent in text:
                    passed = False
                report["checks"].append({
                    "name": name,
                    "command": command,
                    "expected": expected,
                    "exit": code,
                    "passed": passed,
                    "tail": text[-900:],
                })
                return passed

            results = [
                check(
                    "argv_cwd_env_path_and_same_directory_import",
                    "python3 /work/py1/main.py alpha beta",
                    "PY1_CONTRACT_OK",
                    absent="AssertionError",
                ),
                check(
                    "selected_stdlib_closure",
                    "python3 /work/py1/stdlib_probe.py",
                    "PY1_STDLIB_OK json re collections itertools functools math 雪",
                ),
                check(
                    "binary_source_preserved",
                    "python3 /work/py1/byte_probe.py",
                    "PY1_BYTES 5 00580a7fff",
                ),
                check(
                    "missing_module_nonzero",
                    "python3 /work/py1/missing_import.py",
                    "ModuleNotFoundError: No module named 'xos_module_that_does_not_exist'",
                    code="1",
                ),
                check(
                    "syntax_error_nonzero",
                    "python3 /work/py1/syntax_error.py",
                    "SyntaxError: invalid syntax",
                    code="1",
                ),
                check(
                    "unhandled_exception_nonzero",
                    "python3 /work/py1/unhandled.py",
                    "RuntimeError: py1 unhandled marker",
                    code="1",
                ),
            ]
            report["status"] = "passed" if all(results) else "failed"
        finally:
            guest.close()

    output = ROOT / "build/cpython_py1_report.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
