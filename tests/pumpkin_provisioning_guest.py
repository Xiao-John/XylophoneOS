#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise application/catalog atomic publication through real Files and Pumpkin guest IPC.

Faults are injected at the independent authority's CAS/ACK boundary. This is
not a physical arbitrary-power-loss or storage-controller qualification.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import time

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "scripts"))
from boot_smoke import Guest
from make_work_disk import create_fat32
from pumpkin_generation_authority import generation_authority, generation_mark, publish_result
from pumpkin_anchored_guest import (binding, digest, sparse_snapshot, packet, receive, realm, blank,
                                   frame_size, header, mark_struct, ready, read, publish, finish, result_codes)
from task_smoke import pump, send_bytes


def make_disk(path):
    create_fat32(path, 512)
    public_sectors = path.stat().st_size // 512
    descriptor = bytearray(512)
    struct.pack_into("<8sIIQ", descriptor, 0, b"XOSPRIV1", 2, 32, public_sectors)
    with path.open("r+b") as image:
        image.seek(public_sectors * 512)
        image.write(descriptor)
        image.truncate((public_sectors + 65) * 512)
        image.flush()
        os.fsync(image.fileno())


def mark(value):
    return None if value == blank else generation_mark(*mark_struct.unpack(value), provisioning=True)


def boot(system, disk, output, name, scenario, authority, fault="none"):
    guest = Guest(system / "xos-install.iso", name, iso=True, work_disk=disk, log_dir=output)
    evidence = {"scenario": scenario, "injected_fault": fault, "events": [], "status": "failed"}
    try:
        evidence["qemu_version"] = subprocess.check_output([guest.command[0], "--version"], text=True).splitlines()[0]
        guest.expect(b"xos64> ", timeout=35)
        start = len(guest.output)
        send_bytes(guest, b"run\r")
        preamble = packet(ready, 0, 0)[:header.size]
        guest.expect(preamble, start=start, timeout=30)
        offset = guest.output.index(preamble, start)
        for sequence in range(100):
            operation, result, expected, value = receive(guest, offset, sequence)
            offset += frame_size
            if operation == ready:
                assert sequence == 0 and result == 0 and expected == blank and value == blank
                reply = packet(ready, scenario, sequence)
            elif operation == read:
                selected = authority.read()
                encoded = blank if selected is None else mark_struct.pack(
                    selected.realm, selected.revision, selected.length, selected.checksum)
                evidence["events"].append({"read_revision": None if selected is None else selected.revision})
                reply = packet(read, 1 if selected is None else 0, sequence, encoded)
            elif operation == publish:
                previous, candidate = mark(expected), mark(value)
                assert candidate is not None
                assert previous == authority.read()
                injected = candidate.revision == 8 and fault != "none"
                if injected and fault in ("rejected_cas", "uncommitted_unknown"):
                    outcome = publish_result.unchanged if fault == "rejected_cas" else publish_result.outcome_unknown
                else:
                    outcome = authority.publish(previous, candidate)
                    assert outcome == publish_result.committed
                    if injected and fault == "committed_unknown":
                        outcome = publish_result.outcome_unknown
                evidence["events"].append({"candidate_revision": candidate.revision, "reply": outcome.name,
                                           "selected_revision": authority.read().revision})
                reply = packet(publish, result_codes[outcome], sequence)
            else:
                assert operation == finish and expected == blank and value == blank
                evidence["finish_code"] = result
                send_bytes(guest, packet(finish, 0, sequence))
                pump(guest, 0.15)
                guest.qmp("quit")
                assert guest.process.wait(timeout=10) == 0
                assert result == 1, f"{name}: production guest supervisor failed: {result}"
                evidence["status"] = "passed"
                evidence["authority_revision"] = authority.read().revision
                return evidence
            send_bytes(guest, reply)
        raise AssertionError("bounded protocol exchange count exhausted")
    finally:
        guest.close()
        (output / f"{name}.json").write_text(json.dumps(evidence, indent=2) + "\n")


def run(system, output):
    output.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((system / "manifest.json").read_text())
    assert manifest.get("pumpkin_provisioning_store") == 1
    report = {"status": "failed", "system": binding(system), "profile": "provisioning-v1/private-region-v2",
              "fault_scope": "real guest Files writes and IPC; injected authority CAS/ACK outcomes; no physical power-loss claim",
              "cases": {}}
    try:
        for fault in ("none", "rejected_cas", "committed_unknown", "uncommitted_unknown"):
            with tempfile.TemporaryDirectory(prefix="pumpkin_provisioning_") as directory:
                scratch = Path(directory)
                provider_root = scratch / "independent"
                provider_root.mkdir(mode=0o700)
                authority = generation_authority(provider_root, realm, provisioning=True)
                authority.provision()
                disk = scratch / "work.img"
                old_disk = scratch / "old.img"
                make_disk(disk)
                initial = boot(system, disk, output, f"{fault}_initial", 1, authority)
                assert initial["authority_revision"] == 7
                sparse_snapshot(disk, old_disk)
                scenario = 15 if fault == "none" else 16 if fault == "rejected_cas" else 17
                mutation = boot(system, disk, output, f"{fault}_mutation", scenario, authority, fault)
                published = fault in ("none", "committed_unknown")
                assert mutation["authority_revision"] == (8 if published else 7)
                selected = boot(system, disk, output, f"{fault}_cold_recovery", 18 if published else 2, authority)
                assert selected["authority_revision"] == (8 if published else 7)
                case = {"initial": initial["status"], "mutation": mutation["status"], "cold_recovery": selected["status"],
                        "selected": "new data + new installation metadata" if published else "old data + old installation metadata",
                        "selected_revision": selected["authority_revision"]}
                if published:
                    stale = boot(system, old_disk, output, f"{fault}_stale_disk", 3, authority)
                    case["stale_disk_denied"] = stale["status"] == "passed"
                report["cases"][fault] = case
        assert binding(system) == report["system"]
        report["status"] = "passed"
        report["checks"] = ["real private Files v2 lease", "ordinary application credential authorization",
                            "cross-application credential denied", "ordinary catalog publication denied",
                            "revoked application denied on two live sessions", "durable revoked state",
                            "atomic application data and installation receipt recovery", "exact protected-root recovery",
                            "stale work disk denied", "outcome_unknown stops daemon without retry"]
        print("PASS real guest provisioning: old/new atomic recovery, authority fault injection, durable app denial, stale disk", flush=True)
    finally:
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system-build", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    run(options.system_build.resolve(), options.output.resolve())
