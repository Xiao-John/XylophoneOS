# SPDX-License-Identifier: Apache-2.0
"""Cold-boot Xsh/dash and explicit demo behavior on paired system builds."""
import argparse
import json
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import command, resources
from shell_launch_support import bind_system, check_hash, check_result, sha
from task_smoke import send_bytes
from work_disk import transfer


DEMO_PIDS = {1, 2, 3, 4}
C_DONE = b"GLIBC_KIT_C_OK 2.44"
CPP_DONE = b"GLIBC_KIT_CPP_OK vector thread exception"
DASH_DONE = b"GLIBC_KIT_DASH_OK"


def session(guest):
    return command(guest, "ps", b"xsh> ")


def demos(output):
    return DEMO_PIDS & {int(pid) for pid in re.findall(rb"pid=(\d+) name=", output)}


def run_case(image, name, files, output, row, action):
    with tempfile.TemporaryDirectory(prefix="xos_boot_launch_") as folder:
        disk = Path(folder) / "work.img"
        create_fat32(disk, 512)
        for path in ("/usr", "/usr/bin", "/state"):
            transfer(disk, "mkdir", path)
        for path, source in files.items():
            transfer(disk, "import", path, source)
        script = Path(folder) / "app.sh"
        script.write_text("set -e\nkit_c\n/usr/bin/kit_cpp\necho GLIBC_KIT_DASH_OK\n")
        transfer(disk, "import", "/state/app.sh", script)
        state = Path(folder) / "user.txt"
        state.write_bytes(b"glibc-user-data\n")
        transfer(disk, "import", "/state/user.txt", state)
        guest = Guest(image, name, work_disk=disk, log_dir=output)
        try:
            guest.expect(b"xos64> ", timeout=40)
            start = len(guest.output)
            send_bytes(guest, b"run\r")
            guest.expect(b"[sched] event=start tasks=8", start=start, timeout=40)
            guest.expect_supervisor(trace=True, start=start, timeout=40)
            action(guest, row)
            row["status"] = "passed"
        finally:
            guest.close()


def cold(guest, row, first, markers, *, legacy=False):
    before = resources(guest)
    initial = session(guest)
    row.update(resources_before=before, processes_before=initial.decode("utf-8", "replace"))
    assert before[1] == 7 and demos(initial) == DEMO_PIDS
    if first == "/usr/bin/kit_c":
        command(guest, "/state/not-installed", b"not found")
        assert demos(session(guest)) == DEMO_PIDS
        assert resources(guest) == before
    observed = command(guest, first, b"xsh> ", timeout=180)
    row["output"] = observed.decode("utf-8", "replace")
    if legacy:
        check_result(observed, 126)
        assert b"Resource temporarily unavailable" in observed and C_DONE not in observed
        assert demos(session(guest)) == DEMO_PIDS
        assert resources(guest) == before
        return
    check_result(observed, 0, markers)
    stopped = [observed.index(f"event=killed_by_supervisor pid={pid}".encode()) for pid in DEMO_PIDS]
    assert max(stopped) < observed.index(b"[loader] started")
    quiet = resources(guest)
    row["resources_after"] = quiet
    assert quiet[0] > before[0] and quiet[1] == before[1] - 4 and quiet[2] == before[2]
    assert not demos(session(guest))
    other = command(guest, "/usr/bin/kit_cpp", b"xsh> ", timeout=120)
    check_result(other, 0, (CPP_DONE,))
    assert resources(guest) == quiet


def keep_and_stop(guest, row):
    command(guest, "demo keep", b"demo: keep")
    guest.expect(b"ping", start=len(guest.output), timeout=15)
    before = resources(guest)
    assert before[1] == 7 and demos(session(guest)) == DEMO_PIDS
    observed = command(guest, "/usr/bin/kit_c", b"xsh> ", timeout=120)
    check_result(observed, 0, (C_DONE,))
    assert demos(session(guest)) == DEMO_PIDS and resources(guest) == before
    command(guest, "demo quiet", b"demo tasks stopped")
    quiet = resources(guest)
    assert quiet[0] > before[0] and quiet[1] == before[1] - 4 and quiet[2] == before[2]
    assert not demos(session(guest))
    command(guest, "demo quiet", b"demo tasks already stopped")
    observed = command(guest, "dash /state/app.sh", b"xsh> ", timeout=180)
    check_result(observed, 0, (C_DONE, CPP_DONE, DASH_DONE))
    assert resources(guest) == quiet
    row.update(resources_before=before, resources_after=quiet)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", required=True, type=Path)
    parser.add_argument("--control-system", required=True, type=Path)
    parser.add_argument("--sdk-app-evidence", required=True, type=Path,
                        help="directory with the qualified SDK selection C/C++ ELFs and build receipts")
    parser.add_argument("--dash", required=True, type=Path)
    parser.add_argument("--dash-receipt", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    system, control = bind_system(args.system), bind_system(args.control_system)
    assert system.get("quiet_demos_on_launch") is True
    assert not control.get("quiet_demos_on_launch") and system["sources"] == control["sources"]
    assert system["build_id"] != control["build_id"]
    dash = json.loads(args.dash_receipt.read_text())
    check_hash(args.dash, dash["sha256"], "dash ELF")
    files = {"/usr/bin/dash": args.dash}
    app_input = {}
    for language in ("c", "cpp"):
        directory = args.sdk_app_evidence
        elf = directory / f"kit_{language}.elf"
        receipt = directory / f"{language}-external-build.json"
        checks = json.loads(receipt.read_text())
        assert checks["runtime_family"] == "glibc"
        check_hash(elf, checks["output_sha256"], f"{language} application")
        files[f"/usr/bin/kit_{language}"] = elf
        app_input[language] = {"receipt_sha256": sha(receipt), "elf_sha256": sha(elf)}
    args.output.mkdir(parents=True, exist_ok=False)
    report = {"status": "failed", "cases": [], "apps": app_input,
              "dash_sha256": sha(args.dash), "dash_receipt_sha256": sha(args.dash_receipt),
              "candidate_build_id": system["build_id"], "control_build_id": control["build_id"],
              "candidate_iso_sha256": system["artifacts"]["xos-install.iso"]["sha256"],
              "control_iso_sha256": control["artifacts"]["xos-install.iso"]["sha256"]}
    candidate = args.system / "xos-install.iso"
    legacy = args.control_system / "xos-install.iso"
    try:
        for name, image, action in (
            ("legacy-cold-dash", legacy,
             lambda g, r: cold(g, r, "dash /state/app.sh", (), legacy=True)),
            ("candidate-cold-xsh", candidate,
             lambda g, r: cold(g, r, "/usr/bin/kit_c", (C_DONE,))),
            ("candidate-cold-dash", candidate,
             lambda g, r: cold(g, r, "dash /state/app.sh", (C_DONE, CPP_DONE, DASH_DONE))),
            ("candidate-explicit-demo", candidate, keep_and_stop),
        ):
            row = {"name": name, "status": "failed"}
            report["cases"].append(row)
            run_case(image, name, files, args.output, row, action)
        report["status"] = "passed"
    finally:
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "cases": len(report["cases"])}, sort_keys=True))


if __name__ == "__main__":
    main()
