#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run durable Pumpkin with disposable files slots and private test credentials."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "scripts"))
from build_pumpkin_daemon import sha
from process_smoke import command, resources
from pumpkin_private_region_guest import boot, create_test_image, sector_size, slot_size, tail_bytes
from task_smoke import pump
from work_disk import transfer
from xos_app import tree_receipt


def binding(system, dash_receipt):
    manifest = json.loads((system / "manifest.json").read_text())
    if not manifest.get("pumpkin_durable_probe"):
        raise ValueError("system is missing the disposable daemon profile")
    if any(sha(root / name) != expected for name, expected in manifest["sources"].items()):
        raise ValueError("system source mismatch")
    names = ("xos-install.iso", "user_files.image.elf", "user_supervisor.image.elf",
             "user_pumpkin_durable.image.elf", "user_p2_auth_probe.image.elf")
    artifacts = {name: sha(system / name) for name in names}
    if artifacts != {name: manifest["artifacts"][name]["sha256"] for name in names}:
        raise ValueError("system artifact mismatch")
    dash = json.loads(dash_receipt.read_text())
    dash_binary = root / dash["elf"]
    if sha(dash_binary) != dash["sha256"] or sha(system / "sdk/manifest.json") != dash["sdk_manifest_sha256"]:
        raise ValueError("dash is not bound to that SDK")
    return ({"build_id": manifest["build_id"], "manifest_sha256": sha(system / "manifest.json"),
             "artifacts": artifacts, "sdk_sha256": tree_receipt(system / "sdk")[0],
             "dash_sha256": dash["sha256"], "dash_receipt_sha256": sha(dash_receipt)}, dash_binary)


def run(system, dash_receipt, output):
    output.relative_to(root / "build")
    output.mkdir(parents=True, exist_ok=False)
    report = {"status": "not_run", "runner_sha256": sha(Path(__file__)), "checks": {},
              "not_run": ["production_anti_rollback", "physical_power_loss", "production_enrollment",
                          "authenticated_full_guest_reboot_with_retained_client_key"]}
    guest = None
    try:
        report["system"], dash = binding(system, dash_receipt)
        with tempfile.TemporaryDirectory(prefix="pumpkin_durable_") as directory:
            temp = Path(directory)
            disk = temp / "work.img"
            cutoff = create_test_image(disk, "isolated")
            transfer(disk, "mkdir", "/bin")
            transfer(disk, "import", "/bin/dash", dash)
            transfer(disk, "import", "/bin/pumpkin_durable_client.elf", system / "user_p2_auth_probe.image.elf")
            script = temp / "pumpkin_auth.sh"
            script.write_text("/bin/pumpkin_durable_client.elf\n")
            transfer(disk, "import", "/bin/pumpkin_auth.sh", script)
            report["script_sha256"] = sha(script)
            before = tail_bytes(disk, cutoff)
            checks = [("cycle", "cycle-pass"), ("check", "reboot-pass")]
            for mode, expected in checks:
                guest = boot(system, output, mode, disk)
                command(guest, "demo quiet", b"demo tasks")
                pump(guest, 0.2)
                baseline = resources(guest)
                observed = command(guest, "pumpkin-durable-test " + mode, b"PUMPKIN_DURABLE " + expected.encode(),
                                   timeout=45)
                if b"PUMPKIN_DURABLE_FAIL" in observed or (
                    mode == "cycle" and b"PUMPKIN_DURABLE dash-auth-pass" not in observed
                ):
                    raise AssertionError(observed[-5000:])
                after = resources(guest)
                if after != baseline:
                    raise AssertionError(f"{mode}: guest resources differ from baseline")
                guest.close()
                guest = None
                retained = tail_bytes(disk, cutoff)
                if retained[:sector_size] != before[:sector_size]:
                    raise AssertionError("test device descriptor changed")
                for offset in (sector_size, sector_size + slot_size):
                    if retained[offset:offset + 8] != b"PUMTEST1":
                        raise AssertionError("missing acknowledged disk frame")
                if mode == "check" and retained != before:
                    raise AssertionError("reboot lookup changed account slots")
                report["checks"][mode] = {"status": "passed", "resources": after,
                                           "tail_sha256": hashlib.sha256(retained).hexdigest()}
                before = retained
            report["checks"]["dash"] = {"status": "passed", "scope": "authenticate and logout using a private pipe"}
        if report["system"] != binding(system, dash_receipt)[0]:
            raise ValueError("qualification inputs changed during the guest test")
        report["status"] = "passed_subset"
    except BaseException as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        if guest:
            guest.close()
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print("PASS native durable daemon authenticated through xsh and dash, revoked and restarted")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", type=Path, required=True)
    parser.add_argument("--dash-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.system.resolve(strict=True), args.dash_receipt.resolve(strict=True), args.output.resolve())


if __name__ == "__main__":
    main()
