#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Probe current XOS file retention and authority on a disposable work disk."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "scripts"))
from boot_smoke import Guest
from build_pumpkin_daemon import sha, source_hashes
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import pump, send_bytes
from work_disk import transfer
from xos_app import tree_receipt

probe = "pumpkin_storage_probe.elf"
guest_probe = "/bin/" + probe


def disk_hash(disk):
    with disk.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(system, fixture, output, dash_receipt):
    output.relative_to(root / "build")
    output.mkdir(parents=True, exist_ok=False)
    report = {"status": "not_run", "runner_sha256": sha(Path(__file__)), "boots": [],
              "not_run": ["sudden_power_loss", "torn_device_writes", "rollback_anchor", "private_store"]}
    guest = None
    try:
        manifest_file = system / "manifest.json"
        receipt_file = fixture / "receipt.json"
        manifest = json.loads(manifest_file.read_text())
        receipt = json.loads(receipt_file.read_text())
        dash = json.loads(dash_receipt.read_text())
        dash_binary = root / dash["elf"]

        def check_inputs():
            for name, expected in manifest["sources"].items():
                if sha(root / name) != expected:
                    raise ValueError(f"system source mismatch: {name}")
            image = system / "xos-install.iso"
            if sha(image) != manifest["artifacts"][image.name]["sha256"]:
                raise ValueError("manifest ISO mismatch")
            if tree_receipt(system / "sdk")[0] != receipt["sdk_tree_sha256"]:
                raise ValueError("fixture SDK mismatch")
            if receipt["profile"] != "pumpkin-storage-probe" or receipt["sources"] != source_hashes(True):
                raise ValueError("storage fixture source mismatch")
            if receipt["artifacts"] != {probe: sha(fixture / probe)}:
                raise ValueError("storage fixture binary mismatch")
            if sha(dash_binary) != dash["sha256"] or sha(system / "sdk/manifest.json") != dash[
                "sdk_manifest_sha256"
            ]:
                raise ValueError("dash differs from its receipt or system SDK")

        check_inputs()
        report.update(build_id=manifest["build_id"], system_manifest_sha256=sha(manifest_file),
                      image_sha256=sha(system / "xos-install.iso"), fixture_receipt_sha256=sha(receipt_file),
                      sdk_tree_sha256=receipt["sdk_tree_sha256"], artifact_sha256=receipt["artifacts"][probe],
                      dash_receipt_sha256=sha(dash_receipt), dash_sha256=dash["sha256"])
        with tempfile.TemporaryDirectory(prefix="pumpkin_storage_") as temporary:
            base = Path(temporary)
            disk = base / "work.img"
            create_fat32(disk, 512)
            transfer(disk, "mkdir", "/bin")
            transfer(disk, "import", guest_probe, fixture / probe)
            transfer(disk, "import", "/bin/dash", dash_binary)
            script = base / "storage.sh"
            script.write_text(f'{guest_probe} "$1"\n')
            transfer(disk, "import", "/bin/storage.sh", script)
            report["script_sha256"] = sha(script)

            scenarios = [
                [("xsh", "create", "initial-synchronized", 0),
                 ("dash", "interrupt", "staged-prefix-exit", 70),
                 ("xsh", "check-initial", "initial-retained", 0)],
                [("dash", "check-initial", "initial-retained", 0),
                 ("xsh", "other-writer", "ordinary-session-read-and-replaced", 0)],
                [("xsh", "check-changed", "changed-retained", 0),
                 ("dash", "check-changed", "changed-retained", 0)],
            ]
            for index, actions in enumerate(scenarios, 1):
                row = {"disk_before_sha256": disk_hash(disk), "steps": []}
                report["boots"].append(row)
                guest = Guest(system / "xos-install.iso", str(output.relative_to(root / "build") / f"boot{index}"),
                              iso=True, work_disk=disk, qmp_enabled=False)
                guest.expect(b"xos64> ", timeout=60)
                send_bytes(guest, b"run\r")
                guest.expect_supervisor(trace=True, timeout=60)
                command(guest, "demo quiet", b"demo tasks")
                pump(guest, 0.2)
                row["baseline"] = resources(guest)
                for entry, mode, marker, exit_code in actions:
                    invocation = guest_probe if entry == "xsh" else "/bin/dash /bin/storage.sh"
                    observed = command(guest, f"{invocation} {mode}", b"kind=exited code=", timeout=40)
                    match = re.search(f"PUMPKIN_STORAGE {marker} pid=(\\d+)".encode(), observed)
                    result = re.search(rb"\[wait\].*kind=exited code=(-?\d+)", observed)
                    if not match or not result or int(result.group(1)) != exit_code:
                        raise AssertionError(observed[-5000:])
                    after = resources(guest)
                    if after != row["baseline"]:
                        raise AssertionError(f"{entry}/{mode}: guest resources differ from baseline")
                    row["steps"].append({"entry": entry, "mode": mode, "exit": exit_code,
                                         "probe_pid": int(match.group(1)), "resources": after})
                guest.close()
                guest = None
                row["disk_after_sha256"] = disk_hash(disk)
        check_inputs()
        report["status"] = "passed_subset"
        report["observed"] = {
            "synchronized_snapshot_retention": "passed",
            "precommit_writer_exit_retains_previous_snapshot": "passed",
            "ordinary_direct_block_and_maintenance_access": "denied",
            "ordinary_session_read_and_replacement_of_candidate_path": "allowed",
            "pumpkin_private_store_qualification": "blocked_by_files_authority",
        }
    except BaseException as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        if guest:
            guest.close()
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print("PASS Pumpkin storage feasibility: retention and independent ordinary file access")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("system", "fixture", "output", "dash-receipt"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    run(args.system.resolve(strict=True), args.fixture.resolve(strict=True), args.output.resolve(),
        args.dash_receipt.resolve(strict=True))


if __name__ == "__main__":
    main()
