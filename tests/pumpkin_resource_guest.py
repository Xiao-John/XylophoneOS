#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise one sealed Pumpkin-owned file through real IPC on the ordinary image."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import secrets
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from boot_smoke import Guest
from build_pumpkin_daemon import sha, source_hashes
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import pump, send_bytes
from work_disk import transfer
from xos_app import tree_receipt

ARTIFACT = "pumpkin_resource_probe.elf"
PLATFORM_FLAGS = ("files_private_storage_probe", "files_private_client_probe",
                  "pumpkin_durable_probe", "pumpkin_anchored_probe")
MARKER = (b"PUMPKIN_BLOB_PASS owner_read native_right stale_incarnation wrong_account live_session_copy "
          b"revoked direct_files_denied")


def verify_inputs(system, fixture):
    manifest = json.loads((system / "manifest.json").read_text())
    if any(manifest.get(flag) for flag in PLATFORM_FLAGS):
        raise ValueError("The sealed-resource probe must run on an ordinary image")
    for name, digest in manifest["sources"].items():
        if sha(ROOT / name) != digest:
            raise ValueError("System source changed: " + name)
    for name, value in manifest["artifacts"].items():
        if sha(system / name) != value["sha256"]:
            raise ValueError("System artifact changed: " + name)
    receipt = json.loads((fixture / "receipt.json").read_text())
    if (receipt["profile"] != "pumpkin-resource-probe"
            or receipt["sources"] != source_hashes(resource_probe=True)
            or receipt["sdk_tree_sha256"] != tree_receipt(system / "sdk")[0]
            or receipt["artifacts"] != {ARTIFACT: sha(fixture / ARTIFACT)}
            or receipt["libc_linked"]):
        raise ValueError("The resource fixture does not match the ordinary system SDK")
    return manifest, receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("system", "fixture", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    system, fixture, output = (getattr(args, name).resolve() for name in ("system", "fixture", "output"))
    output.mkdir(parents=True)
    guest = None
    report = {"status": "failed", "runner_sha256": sha(Path(__file__))}
    try:
        manifest, receipt = verify_inputs(system, fixture)
        image = system / "xos-install.iso"
        report.update(build_id=manifest["build_id"], system_manifest_sha256=sha(system / "manifest.json"),
                      image_sha256=sha(image), fixture_receipt_sha256=sha(fixture / "receipt.json"),
                      fixture_sha256=receipt["artifacts"][ARTIFACT])
        with tempfile.TemporaryDirectory(prefix="xos_pumpkin_resource_") as temporary:
            disk = Path(temporary) / "ordinary.img"
            create_fat32(disk, 512)
            transfer(disk, "mkdir", "/bin")
            transfer(disk, "import", f"/bin/{ARTIFACT}", fixture / ARTIFACT)
            guest = Guest(image, "resources", iso=True, work_disk=disk, log_dir=output, qmp_enabled=False)
            report["qemu_command"] = guest.command
            guest.expect(b"xos64> ", timeout=60)
            send_bytes(guest, b"run\r")
            guest.expect_supervisor(trace=True, timeout=60)
            command(guest, "demo quiet", b"demo tasks")
            pump(guest, 0.2)
            baseline = resources(guest)
            for _ in range(2):
                name = "pumpkin-" + secrets.token_hex(8)
                captured = command(guest, f"exec-driver /bin/{ARTIFACT} broker {name}", MARKER, timeout=45)
                if not re.search(rb"\[wait\].*kind=exited code=0", captured) or resources(guest) != baseline:
                    raise AssertionError(captured[-5000:])
            report.update(status="passed", rounds=2, restored_resources=baseline,
                          scope=["native_endpoint_peer", "sealed_anonymous_files", "owner_read",
                                 "missing_native_right", "stale_incarnation", "wrong_account", "copied_live_session",
                                 "revoked_owner", "foreign_files_handle"])
        verify_inputs(system, fixture)
    except BaseException as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        if guest:
            guest.close()
            report["serial_sha256"] = hashlib.sha256(guest.output).hexdigest()
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print("PASS sealed Pumpkin resource over native IPC on the ordinary image")


if __name__ == "__main__":
    main()
