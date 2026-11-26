#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify the opt-in files private region over abrupt QEMU exits and new boots."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import struct
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
sector_size = 512
slot_size = 9 * sector_size
prefix = 512 * 1024 * 1024


def sector_write(stream, sector, data):
    stream.seek(sector * sector_size)
    stream.write(data)


def create_test_image(path, layout):
    create_fat32(path, 512)
    if layout == "ordinary":
        return prefix
    public_sectors = prefix // sector_size - (1 if layout == "undersized" else 0)
    public_size = public_sectors * sector_size
    descriptor = bytearray(sector_size)
    struct.pack_into("<8sIIQ", descriptor, 0, b"XOSPRIV1", 1, 9, public_sectors)
    with path.open("r+b") as disk:
        if layout == "undersized":
            disk.truncate(public_size)
        disk.truncate(public_size + sector_size + 2 * slot_size)
        sector_write(disk, public_sectors, descriptor)
        # Valid fixture images use the public size in primary and backup VBRs.
        for sector in (0, 6):
            disk.seek(sector * sector_size)
            boot = bytearray(disk.read(sector_size))
            extent = public_sectors + (1 if layout == "overlap" and sector == 0 else 0)
            struct.pack_into("<I", boot, 32, extent)
            sector_write(disk, sector, boot)
        if layout == "bad_descriptor":
            sector_write(disk, public_sectors, b"INVALID!")
        disk.flush()
        os.fsync(disk.fileno())
    return public_size


def tail_bytes(disk, public_size):
    with disk.open("rb") as stream:
        stream.seek(public_size)
        return stream.read()


def expected_slots(count):
    return b"".join(
        bytes((0x47 + 29 * slot + 13 * byte + byte // sector_size) & 0xff for byte in range(slot_size))
        if slot < count else bytes(slot_size) for slot in range(2)
    )


def verify_system(system, expected_profile):
    manifest = json.loads((system / "manifest.json").read_text())
    if bool(manifest.get("files_private_storage_probe")) != expected_profile:
        raise ValueError("system has the wrong private storage profile")
    for name, expected in manifest["sources"].items():
        if sha(root / name) != expected:
            raise ValueError(f"system source mismatch: {name}")
    if sha(system / "xos-install.iso") != manifest["artifacts"]["xos-install.iso"]["sha256"]:
        raise ValueError("manifest ISO mismatch")
    return {"build_id": manifest["build_id"], "iso_sha256": sha(system / "xos-install.iso"),
            "manifest_sha256": sha(system / "manifest.json"), "sdk_sha256": tree_receipt(system / "sdk")[0]}


def verify_fixture(fixture, sdk_hash):
    receipt = json.loads((fixture / "receipt.json").read_text())
    if receipt["profile"] != "pumpkin-storage-probe" or receipt["sdk_tree_sha256"] != sdk_hash or (
        receipt["sources"] != source_hashes(True) or receipt["artifacts"] != {probe: sha(fixture / probe)}
    ):
        raise ValueError("storage probe does not match the source or SDK")
    return {"receipt_sha256": sha(fixture / "receipt.json"), "elf_sha256": sha(fixture / probe)}


def boot(system, output, label, disk):
    guest = Guest(system / "xos-install.iso", str(output.relative_to(root / "build") / label),
                  iso=True, work_disk=disk, qmp_enabled=False)
    try:
        guest.expect(b"xos64> ", timeout=60)
        send_bytes(guest, b"run\r")
        guest.expect_supervisor(trace=True, timeout=60)
        return guest
    except BaseException:
        guest.close()
        raise


def public_use(guest, invocation, mode, label):
    command(guest, "demo quiet", b"demo tasks")
    pump(guest, 0.2)
    baseline = resources(guest)
    observed = command(guest, f"{invocation} {mode}", b"kind=exited code=", timeout=40)
    if f"PUMPKIN_STORAGE {label}".encode() not in observed or not re.search(
        rb"\[wait\].*kind=exited code=0", observed
    ):
        raise AssertionError(observed[-5000:])
    if resources(guest) != baseline:
        raise AssertionError("guest process resources differ from baseline")
    return baseline


def run(options):
    output = options.output.resolve()
    output.relative_to(root / "build")
    output.mkdir(parents=True, exist_ok=False)
    report = {"status": "not_run", "runner_sha256": sha(Path(__file__)), "checks": {},
              "not_run": ["physical_power_loss", "mid_write_interruption", "durable_generation", "caller_grant"]}
    guest = None

    def verify_inputs():
        isolated = verify_system(options.system, True)
        ordinary = verify_system(options.ordinary_system, False)
        dash = json.loads(options.dash_receipt.read_text())
        dash_binary = root / dash["elf"]
        if sha(dash_binary) != dash["sha256"] or sha(options.system / "sdk/manifest.json") != dash[
            "sdk_manifest_sha256"
        ]:
            raise ValueError("dash is not bound to the opt-in SDK")
        return {"isolated": isolated, "ordinary": ordinary,
                "isolated_probe": verify_fixture(options.fixture, isolated["sdk_sha256"]),
                "ordinary_probe": verify_fixture(options.ordinary_fixture, ordinary["sdk_sha256"]),
                "dash_receipt_sha256": sha(options.dash_receipt), "dash_elf_sha256": sha(dash_binary)}, dash_binary

    try:
        report["inputs"], dash_binary = verify_inputs()
        with tempfile.TemporaryDirectory(prefix="xos_private_region_") as directory:
            temp = Path(directory)
            disk = temp / "isolated.img"
            public_size = create_test_image(disk, "isolated")
            transfer(disk, "mkdir", "/bin")
            transfer(disk, "import", "/bin/" + probe, options.fixture / probe)
            transfer(disk, "import", "/bin/dash", dash_binary)
            script = temp / "private_public.sh"
            script.write_text(f'/bin/{probe} "$1"\n')
            transfer(disk, "import", "/bin/private_public.sh", script)
            descriptor = tail_bytes(disk, public_size)[:sector_size]
            mode_checks = [
                ("xsh_first", f"/bin/{probe}", "private-create", "private-band-public-create", 1),
                ("dash_reboot", "/bin/dash /bin/private_public.sh", "private-check", "private-band-public-retained", 2),
                ("xsh_reboot", f"/bin/{probe}", "private-check", "private-band-public-retained", 2),
            ]
            for label, invocation, mode, marker, count in mode_checks:
                guest = boot(options.system, output, label, disk)
                baseline = public_use(guest, invocation, mode, marker)
                # Kill the emulator only after the guest’s private and public
                # synchronous writes have completed. No normal QEMU shutdown.
                guest.process.kill()
                if guest.process.wait(timeout=5) != -signal.SIGKILL:
                    raise AssertionError("QEMU was not stopped by SIGKILL")
                guest.close()
                guest = None
                entire_tail = tail_bytes(disk, public_size)
                if entire_tail != descriptor + expected_slots(count):
                    raise AssertionError(f"{label}: private sectors did not match after guest sync and abrupt exit")
                report["checks"][label] = {"status": "passed", "resources": baseline,
                                           "slot_count": count, "tail_sha256": hashlib.sha256(entire_tail).hexdigest()}

            for layout in ("bad_descriptor", "overlap", "undersized"):
                invalid = temp / f"{layout}.img"
                invalid_size = create_test_image(invalid, layout)
                before = tail_bytes(invalid, invalid_size)
                guest = boot(options.system, output, layout, invalid)
                if b"[files] bootstrap-stat error=-7" not in guest.output:
                    raise AssertionError(f"{layout}: invalid layout did not fail files startup")
                command(guest, "sync", b"maintenance: persistent recovery required; command blocked")
                guest.close()
                guest = None
                if tail_bytes(invalid, invalid_size) != before:
                    raise AssertionError(f"{layout}: private region modified after layout rejection")
                report["checks"][layout] = {"status": "rejected_without_private_writes"}

            ordinary_disk = temp / "ordinary.img"
            create_test_image(ordinary_disk, "ordinary")
            transfer(ordinary_disk, "mkdir", "/bin")
            transfer(ordinary_disk, "import", "/bin/" + probe, options.ordinary_fixture / probe)
            guest = boot(options.ordinary_system, output, "default_control", ordinary_disk)
            baseline = public_use(guest, f"/bin/{probe}", "private-create", "private-band-public-create")
            report["checks"]["normal_system_ordinary_disk"] = {"status": "passed", "resources": baseline}
            guest.close()
            guest = None
            if ordinary_disk.stat().st_size != prefix:
                raise AssertionError("normal profile extended the ordinary disk")

        if verify_inputs()[0] != report["inputs"]:
            raise ValueError("verification inputs changed during execution")
        report["status"] = "passed_subset"
    except BaseException as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        if guest:
            guest.close()
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print("PASS opt-in files-only storage across abrupt emulator exits")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("system", "ordinary-system", "fixture", "ordinary-fixture", "dash-receipt", "output"):
        parser.add_argument("--" + arg, type=Path, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
