#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise the immutable Pumpkin slot client and the authenticated boot grant."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "scripts"))
from build_pumpkin_daemon import sha
from process_smoke import command, resources
from pumpkin_private_region_guest import boot, create_test_image, sector_size, slot_size, tail_bytes
from task_smoke import pump
from xos_app import tree_receipt


def binding(system):
    path = system / "manifest.json"
    manifest = json.loads(path.read_text())
    if not manifest.get("files_private_client_probe"):
        raise ValueError("system has no authenticated private client test profile")
    if any(sha(root / name) != expected for name, expected in manifest["sources"].items()):
        raise ValueError("system source mismatch")
    names = ("xos-install.iso", "user_files.image.elf", "user_supervisor.image.elf", "user_p2_store_probe.image.elf")
    artifacts = {name: sha(system / name) for name in names}
    if artifacts != {name: manifest["artifacts"][name]["sha256"] for name in names}:
        raise ValueError("system artifact mismatch")
    return {"build_id": manifest["build_id"], "manifest_sha256": sha(path), "artifacts": artifacts,
            "sdk_sha256": tree_receipt(system / "sdk")[0]}


def run(system, out):
    out.relative_to(root / "build")
    out.mkdir(parents=True, exist_ok=False)
    report = {"status": "not_run", "runner_sha256": sha(Path(__file__)), "boots": [],
              "not_run": ["independent_generation", "physical_power_loss", "production_credentials", "dash"]}
    guest = None
    try:
        report["system"] = binding(system)
        with tempfile.TemporaryDirectory(prefix="pumpkin_files_client_") as directory:
            disk = Path(directory) / "work.img"
            public_size = create_test_image(disk, "isolated")
            previous = tail_bytes(disk, public_size)
            groups = [
                [("exec p2_store_probe check", "no-bootstrap-pipe", 14),
                 ("pumpkin-store-test seed", "synchronized-readback", 0),
                 ("pumpkin-store-test partial", "exit-with-uncommitted-stage", 0),
                 ("pumpkin-store-test check", "reader-verified-retention", 0)],
                [("pumpkin-store-test check", "reader-verified-retention", 0)],
            ]
            for index, checks in enumerate(groups, 1):
                guest = boot(system, out, f"boot{index}", disk)
                command(guest, "demo quiet", b"demo tasks")
                pump(guest, 0.2)
                baseline = resources(guest)
                row = {"baseline": baseline, "checks": []}
                report["boots"].append(row)
                for line, marker, code in checks:
                    output = command(guest, line, f"kind=exited code={code}".encode(), timeout=15)
                    if b"PUMPKIN_FILES_LEASE_FAIL" in output or f"PUMPKIN_FILES_LEASE {marker}".encode() not in output:
                        raise AssertionError(output[-5000:])
                    actual = resources(guest)
                    if actual != baseline:
                        raise AssertionError(f"{line}: resources differ from baseline")
                    row["checks"].append({"command": line, "exit": code, "status": "passed", "resources": actual})
                guest.close()
                guest = None
                retained = tail_bytes(disk, public_size)
                if retained[:sector_size] != previous[:sector_size] or any(retained[-slot_size:]):
                    raise AssertionError("inactive slot or layout changed")
                if index == 1 and retained[sector_size:sector_size + 8] != b"PUMPKIN\0":
                    raise AssertionError("synced slot lacks the expected native snapshot")
                if index == 2 and retained != previous:
                    raise AssertionError("reader or reboot altered persistent state")
                row["tail_sha256"] = hashlib.sha256(retained).hexdigest()
                previous = retained
        if report["system"] != binding(system):
            raise ValueError("inputs changed during the guest checks")
        report["status"] = "passed_subset"
    except BaseException as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        if guest:
            guest.close()
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print("PASS native files grant, lease cleanup and ordinary reboot retention")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.system.resolve(strict=True), args.output.resolve())


if __name__ == "__main__":
    main()
