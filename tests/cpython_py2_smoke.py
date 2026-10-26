# SPDX-License-Identifier: Apache-2.0
"""PY2: interactive input and reboot-persistent JSON in a real XOS guest."""

import argparse
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]
from boot_smoke import Guest
from cpython_py0b_smoke import run
from cpython_py1_smoke import install_stage
from make_work_disk import create_fat32
from process_smoke import command, resources
from stage_cpython import sha256, stage_cpython
from task_smoke import pump, send_bytes
from work_disk import transfer


FIXTURES = ROOT / "tests/fixtures/cpython_py2"


def send_raw(guest, data):
    for value in data:
        guest.process.stdin.write(bytes([value]))
        guest.process.stdin.flush()
        time.sleep(0.003)


def expect_after(guest, marker, start, timeout=20):
    guest.expect(marker, start=start, timeout=timeout)
    return guest.output.find(marker, start) + len(marker)


def boot(image, disk, name):
    guest = Guest(image, name, work_disk=disk)
    guest.expect(b"xos64> ", timeout=30)
    start = len(guest.output)
    send_bytes(guest, b"run\r")
    guest.expect_supervisor(trace=True, start=start, timeout=40)
    pump(guest, 1.0)
    return guest


def reclaimed_pages(data):
    values = [int(value) for value in re.findall(rb"event=reclaimed pid=\d+ pages=(\d+)", data)]
    return max(values) if values else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--image", type=Path, default=ROOT / "build/xos.img")
    args = parser.parse_args()
    work = args.work.resolve(strict=True)
    stage, stage_manifest = stage_cpython(work)
    build_report = json.loads((work / "py0a_report.json").read_text())
    report = {
        "phase": "PY2",
        "status": "failed",
        "build_id": json.loads((ROOT / "build/manifest.json").read_text())["build_id"],
        "xos_image_sha256": sha256(args.image),
        "cpython_fingerprint": stage_manifest["fingerprint"],
        "cpython_profile": build_report["profile"],
        "stage_manifest_sha256": sha256(work / "stage_py1_manifest.json"),
        "stage_file_count": stage_manifest["file_count"],
        "checks": [],
    }
    output_path = ROOT / "build/cpython_py2_report.json"
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix="xos_cpython_py2_") as folder:
            temporary = Path(folder)
            image = temporary / "xos.img"
            disk = temporary / "work.img"
            shutil.copyfile(args.image, image)
            create_fat32(disk, 2048)
            install_stage(disk, stage)
            for guest_path in ("/work", "/work/py2"):
                transfer(disk, "mkdir", guest_path)
            for fixture in sorted(FIXTURES.glob("*.py")):
                transfer(disk, "import", f"/work/py2/{fixture.name}", fixture)

            guest = boot(image, disk, "cpython_py2_first")
            baseline = resources(guest)
            report["resources_before"] = baseline

            # Traditional REPL: remain alive while idle, edit a line, execute a
            # compound statement, then leave through an empty-line Ctrl-D.
            start = len(guest.output)
            send_bytes(guest, b"python3\r")
            guest.expect(b">>> ", start=start, timeout=60)
            pump(guest, 0.7)
            idle_alive = b"kind=exited code=" not in guest.output[start:]
            cursor = len(guest.output)
            send_raw(guest, b"print(6*8)\r")
            cursor = expect_after(guest, b"48", cursor)
            cursor = expect_after(guest, b">>> ", cursor)
            send_raw(guest, b"print(7*7)\n")
            cursor = expect_after(guest, b"49", cursor)
            cursor = expect_after(guest, b">>> ", cursor)
            send_raw(guest, b"def twice(x):\r")
            cursor = expect_after(guest, b"... ", cursor)
            send_raw(guest, b"    return x*2\r")
            cursor = expect_after(guest, b"... ", cursor)
            send_raw(guest, b"\r")
            cursor = expect_after(guest, b">>> ", cursor)
            send_raw(guest, b"print(twice(21))\r")
            cursor = expect_after(guest, b"42", cursor)
            cursor = expect_after(guest, b">>> ", cursor)
            send_raw(guest, b"\x04")
            cursor = expect_after(guest, b"kind=exited code=0", cursor, timeout=30)
            expect_after(guest, b"xsh> ", cursor)
            after = resources(guest)
            repl_output = bytes(guest.output[start:])
            report["checks"].append({
                "name": "basic_repl_idle_compound_ctrl_d",
                "passed": (
                    idle_alive and b"48" in repl_output and b"49" in repl_output
                    and b"42" in repl_output and after == baseline
                ),
                "resources_after": after,
                "reclaimed_pages": reclaimed_pages(repl_output),
                "tail": repl_output[-1800:].decode("utf-8", "replace"),
            })

            # input() shares the same line editor; delay proves an empty UART is
            # not EOF, and backspace must remove the mistyped byte.
            start = len(guest.output)
            send_bytes(guest, b"python3 /work/py2/input_probe.py\r")
            guest.expect(b"name> ", start=start, timeout=60)
            pump(guest, 0.7)
            idle_alive = b"kind=exited code=" not in guest.output[start:]
            send_raw(guest, b"helx\x08lo\r")
            guest.expect(b"PY2_INPUT_OK hello", start=start, timeout=30)
            guest.expect(b"kind=exited code=0", start=start, timeout=30)
            guest.expect(b"xsh> ", start=start, timeout=20)
            after = resources(guest)
            input_output = bytes(guest.output[start:])
            report["checks"].append({
                "name": "input_idle_backspace",
                "passed": idle_alive and after == baseline,
                "resources_after": after,
                "reclaimed_pages": reclaimed_pages(input_output),
                "tail": input_output[-1200:].decode("utf-8", "replace"),
            })

            for name, fixture, marker in (
                ("file_directory_short_io_and_failures", "file_probe.py", "PY2_FILE_OK"),
                ("json_save_utf8", "save_json.py", "PY2_SAVE_OK"),
            ):
                text = run(guest, f"python3 /work/py2/{fixture}", timeout=180)
                after = resources(guest)
                report["checks"].append({
                    "name": name,
                    "passed": marker in text and "kind=exited code=0" in text and after == baseline,
                    "resources_after": after,
                    "reclaimed_pages": reclaimed_pages(text.encode()),
                    "tail": text[-1200:],
                })

            # Escape remains the supervisor's force-cancel path.
            start = len(guest.output)
            send_bytes(guest, b"python3\r")
            guest.expect(b">>> ", start=start, timeout=60)
            send_raw(guest, b"\x1b")
            guest.expect(b"event=cancelled_by_escape", start=start, timeout=30)
            guest.expect(b"xsh> ", start=start, timeout=30)
            after = resources(guest)
            cancel_output = bytes(guest.output[start:])
            report["checks"].append({
                "name": "escape_cancels_repl",
                "passed": after == baseline,
                "resources_after": after,
                "reclaimed_pages": reclaimed_pages(cancel_output),
                "tail": cancel_output[-1200:].decode("utf-8", "replace"),
            })

            command(guest, "sync", b"[files] sync=ok", timeout=30)
            guest.close()
            guest = None

            guest = boot(image, disk, "cpython_py2_reboot")
            reboot_baseline = resources(guest)
            text = run(guest, "python3 /work/py2/load_json.py", timeout=180)
            after = resources(guest)
            report["checks"].append({
                "name": "sync_reboot_json_reload",
                "passed": (
                    "PY2_REBOOT_LOAD_OK 雪 42" in text
                    and "kind=exited code=0" in text
                    and after == reboot_baseline
                ),
                "resources_before": reboot_baseline,
                "resources_after": after,
                "reclaimed_pages": reclaimed_pages(text.encode()),
                "tail": text[-1200:],
            })
            report["status"] = "passed" if all(item["passed"] for item in report["checks"]) else "failed"
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        if guest is not None:
            guest.close()
        output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
