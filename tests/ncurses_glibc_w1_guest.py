#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the existing ncurses width, input and reentry fixtures on the glibc SDK."""

import argparse
import json
from pathlib import Path
import re
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from boot_smoke import Guest
from build_glibc_program import sha
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import send_bytes
from work_disk import transfer
from xypm_sdk_profile import verify_profile

FIXTURES = {"locale": "wide_locale_probe.elf", "reentry": "reentry_probe.elf", "wide": "wide_screen_probe.elf"}
COMPLETED = b"kind=exited code="


def check_inputs(args):
    manifest = json.loads((args.system / "manifest.json").read_text())
    if manifest.get("ncurses_supervisor_probe") or manifest.get("terminal_supervisor_probe"):
        raise ValueError("an ordinary xsh image is required")
    target = json.loads((args.probe / "report.json").read_text())
    consumers = json.loads((args.consumers / "report.json").read_text())
    terminal_data = json.loads((args.terminfo / "receipt.json").read_text())
    profile = json.loads(args.profile.read_text())
    binding = verify_profile(profile, "glibc", args.sdk_build)
    lock_path = ROOT / "src/ports/ncurses/source_lock.json"
    lock = json.loads(lock_path.read_text())
    target_library = args.probe / "build/lib/libncursesw.a"
    config = args.probe / "build/include/ncurses_cfg.h"
    term = args.terminfo / "terminfo/x/xterm"
    if (target.get("runtime_family") != "glibc" or target.get("archive_valid") is not True
            or not target.get("inputs_unchanged") or target["sdk_tree_sha256"] != binding["sdk_tree_sha256"]
            or target["sdk_profile_sha256"] != sha(args.profile)
            or consumers.get("runtime_family") != "glibc"
            or consumers.get("status") != "cross_linked_guest_not_run"
            or consumers["sdk_tree_sha256"] != binding["sdk_tree_sha256"]
            or consumers["probe_report_sha256"] != sha(args.probe / "report.json")
            or target["source_sha256"] != lock["sha256"] or target["source_lock_sha256"] != sha(lock_path)
            or target["archive_sha256"] != sha(target_library)
            or consumers["ncurses_archive_sha256"] != sha(target_library)
            or terminal_data["target_library_sha256"] != sha(target_library)
            or terminal_data["target_report_sha256"] != sha(args.probe / "report.json")
            or terminal_data["target_config_sha256"] != sha(config)
            or terminal_data["source_sha256"] != lock["sha256"]
            or terminal_data["entry"] != "x/xterm" or terminal_data["entry_sha256"] != sha(term)):
        raise ValueError("ncurses, terminfo, fixtures and signed SDK do not match")
    for sources in (manifest["sources"], consumers["source_sha256"]):
        for name, expected in sources.items():
            if sha(ROOT / name) != expected:
                raise ValueError("source bytes differ from the recorded build: " + name)
    for name in ("xos-install.iso", "user_terminal.image.elf"):
        if sha(args.system / name) != manifest["artifacts"][name]["sha256"]:
            raise ValueError("system bytes differ from manifest: " + name)
    for name in FIXTURES.values():
        if sha(args.consumers / name) != consumers["artifacts"][name]:
            raise ValueError("ncurses fixture differs from receipt: " + name)
    return manifest, binding, term


def exercise(guest, name):
    start = len(guest.output)
    send_bytes(guest, f"tty-run /bin/{name}.elf\r".encode())
    result = {}
    if name == "wide":
        stages = ((b"W2_INPUT_READY", b"\x1bOD", b""),
                  (b"W2_UTF8_READY", b"\xe4", b"\xb8\xad\x1bOP"),
                  (b"W2_INVALID_READY", b"\xffA", b""),
                  (b"W2_INVALID_RECOVERY_READY", b"B", b""),
                  (b"W2_COMBINING_READY", b"a\xcc", b"\x81"))
        result["checkpoints"] = []
        for marker, first, rest in stages:
            found = guest.expect_any((marker, COMPLETED, b"xsh: cannot"), start=start, timeout=45)
            if found != marker:
                break
            result["checkpoints"].append(marker.decode())
            send_bytes(guest, first)
            if rest:
                time.sleep(0.05)
                send_bytes(guest, rest)
    guest.expect(b"xsh> ", start=start, timeout=45)
    transcript = bytes(guest.output[start:])
    match = re.search(rb"\[wait\] pid=\d+ kind=(\w+) code=(-?\d+)", transcript)
    if match:
        result.update(outcome=match[1].decode(), exit_code=int(match[2]))
    if name == "wide":
        result["wide_rendered"] = (b"\xe4\xb8\xad\xcc\x81" in transcript and
                                   b"W2_LOCAL_CELL" in transcript and
                                   bool(re.search(rb"\x1b\[[0-9;]*31(?:;[0-9]*)?m", transcript)))
    result["passed"] = (result.get("outcome") == "exited" and result.get("exit_code") == 0
                        and (name != "wide" or result["wide_rendered"]))
    if name == "wide" and not result["passed"]:
        # An early exit can leave the tail of an injected key in xsh's line.
        command(guest, "", b"xsh> ")
    result["resources"] = resources(guest)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("system", "sdk-build", "profile", "probe", "consumers", "terminfo", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--ctype", type=Path, help="stage an explicit C.utf8 LC_CTYPE file on the disposable disk")
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True)
    report = {"status": "failed", "observations": {}}
    guest = None
    try:
        manifest, sdk, term = check_inputs(args)
        image = args.system / "xos-install.iso"
        report.update(build_id=manifest["build_id"], system_manifest_sha256=sha(args.system / "manifest.json"),
                      system_sha256=sha(image), sdk=sdk, probe_report_sha256=sha(args.probe / "report.json"),
                      consumers_report_sha256=sha(args.consumers / "report.json"),
                      terminfo_receipt_sha256=sha(args.terminfo / "receipt.json"), terminfo_sha256=sha(term),
                      ctype_sha256=sha(args.ctype) if args.ctype else None)
        with tempfile.TemporaryDirectory(prefix="xos_glibc_ncurses_") as temporary:
            disk = Path(temporary) / "files.img"
            create_fat32(disk, 512)
            for path in ("/bin", "/usr", "/usr/local", "/usr/local/share", "/usr/local/share/terminfo",
                         "/usr/local/share/terminfo/x"):
                transfer(disk, "mkdir", path)
            if args.ctype:
                for path in ("/usr/lib", "/usr/lib/locale", "/usr/lib/locale/C.utf8"):
                    transfer(disk, "mkdir", path)
                transfer(disk, "import", "/usr/lib/locale/C.utf8/LC_CTYPE", args.ctype)
            transfer(disk, "import", "/usr/local/share/terminfo/x/xterm", term)
            transfer(disk, "import", "/bin/terminal.elf", args.system / "user_terminal.image.elf")
            for name, artifact in FIXTURES.items():
                transfer(disk, "import", f"/bin/{name}.elf", args.consumers / artifact)
            guest = Guest(image, "ncurses_glibc", work_disk=disk, iso=True, log_dir=args.output, qmp_enabled=False)
            report["qemu_command"] = guest.command
            guest.expect(b"xos64> ", timeout=60)
            send_bytes(guest, b"run\r")
            guest.expect_supervisor(trace=True, timeout=60)
            command(guest, "demo quiet", b"demo tasks")
            report["idle_resources"] = resources(guest)
            for name in FIXTURES:
                report["observations"][name] = exercise(guest, name)
            rows = list(report["observations"].values())
            if any(row["resources"] != rows[0]["resources"] for row in rows):
                raise RuntimeError("terminal resources changed between fixtures")
            if all(row["passed"] for row in rows):
                report["status"] = "passed"
            elif any(row["passed"] or row.get("wide_rendered") for row in rows):
                report["status"] = "passed_subset"
        check_inputs(args)
    except BaseException as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        if guest:
            guest.close()
            serial = args.output / "serial.log"
            serial.write_bytes(guest.output)
            report["serial_sha256"] = sha(serial)
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(report["status"])
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
