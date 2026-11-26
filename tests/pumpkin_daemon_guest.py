#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the isolated Pumpkin daemon and probe against an exact system and SDK."""

import argparse
import json
from pathlib import Path
import re
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "scripts"))
from boot_smoke import Guest
from build_pumpkin_daemon import programs, sha, source_hashes
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import pump, send_bytes
from work_disk import transfer
from xos_app import tree_receipt


def run(system, fixture, output, dash_receipt):
    output.relative_to(root / "build")
    output.mkdir(parents=True, exist_ok=False)
    report = {"status": "not_run", "runner_sha256": sha(Path(__file__)),
              "profile": "pumpkin-p1-volatile-test", "checks": {},
              "not_run": ["durable_xos_store", "production_install", "object_service_integration"]}
    guest = None
    try:
        manifest_file = system / "manifest.json"
        receipt_file = fixture / "receipt.json"
        manifest = json.loads(manifest_file.read_text())
        receipt = json.loads(receipt_file.read_text())
        dash = json.loads(dash_receipt.read_text()) if dash_receipt else None
        dash_binary = root / dash["elf"] if dash else None
        entries = {"xsh": "/bin/pumpkin_probe.elf"}
        if not dash:
            report["not_run"].append("dash")

        def check_inputs():
            for name, expected in manifest["sources"].items():
                if sha(root / name) != expected:
                    raise ValueError(f"system source mismatch: {name}")
            image = system / "xos-install.iso"
            if sha(image) != manifest["artifacts"][image.name]["sha256"]:
                raise ValueError("manifest ISO mismatch")
            if tree_receipt(system / "sdk")[0] != receipt["sdk_tree_sha256"]:
                raise ValueError("fixture SDK mismatch")
            if receipt["sources"] != source_hashes():
                raise ValueError("fixture source mismatch")
            if {name: sha(fixture / name) for name in programs} != receipt["artifacts"]:
                raise ValueError("fixture binary mismatch")
            if dash and (sha(dash_binary) != dash["sha256"] or sha(system / "sdk/manifest.json") !=
                         dash["sdk_manifest_sha256"]):
                raise ValueError("dash differs from its receipt or system SDK")

        check_inputs()
        report.update(build_id=manifest["build_id"], system_manifest_sha256=sha(manifest_file),
                      image_sha256=sha(system / "xos-install.iso"), fixture_receipt_sha256=sha(receipt_file),
                      sdk_tree_sha256=receipt["sdk_tree_sha256"], artifacts=receipt["artifacts"])
        with tempfile.TemporaryDirectory(prefix="xos_pumpkin_") as temporary:
            workspace = Path(temporary)
            disk = workspace / "work.img"
            create_fat32(disk, 512)
            transfer(disk, "mkdir", "/bin")
            for name in programs:
                transfer(disk, "import", "/bin/" + name, fixture / name)
            if dash:
                transfer(disk, "import", "/bin/dash", dash_binary)
                script = workspace / "pumpkin.sh"
                script.write_text("/bin/pumpkin_probe.elf\n")
                transfer(disk, "import", "/bin/pumpkin.sh", script)
                entries["dash"] = "/bin/dash /bin/pumpkin.sh"
                report["dash"] = {"artifact_sha256": dash["sha256"], "receipt_sha256": sha(dash_receipt),
                                  "script_sha256": sha(script)}
            report["work_disk_sha256"] = sha(disk)
            guest = Guest(system / "xos-install.iso", str(output.relative_to(root / "build") / "guest"),
                          iso=True, work_disk=disk, qmp_enabled=False)
            guest.expect(b"xos64> ", timeout=60)
            send_bytes(guest, b"run\r")
            guest.expect_supervisor(trace=True, timeout=60)
            command(guest, "demo quiet", b"demo tasks")
            pump(guest, 0.2)
            report["baseline"] = resources(guest)
            expected = b"PUMPKIN_P1_PASS real-ipc volatile-store role-and-session-isolation result-unknown cleanup"
            for entry, line in entries.items():
                observed = command(guest, line, b"kind=exited code=", timeout=40)
                if expected not in observed or b"PUMPKIN_P1_FAIL" in observed or not re.search(
                    rb"\[wait\].*kind=exited code=0", observed
                ):
                    raise AssertionError(observed[-5000:])
                after = resources(guest)
                if after != report["baseline"]:
                    raise AssertionError(f"{entry} guest process resources differ from baseline")
                report["checks"][entry] = {"status": "passed", "command": line, "resources": after}
            check_inputs()
            report["status"] = "passed_subset"
    except BaseException as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        if guest:
            guest.close()
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print("PASS Pumpkin native guest volatile test profile")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dash-receipt", type=Path, help="optional same-SDK dash build receipt")
    args = parser.parse_args()
    run(args.system.resolve(strict=True), args.fixture.resolve(strict=True), args.output.resolve(),
        args.dash_receipt)


if __name__ == "__main__":
    main()
