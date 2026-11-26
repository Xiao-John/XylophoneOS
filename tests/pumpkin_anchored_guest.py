#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify independent Pumpkin generations on three fresh, headless guest boots."""

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
from pumpkin_generation_authority import generation_authority, generation_error, generation_mark, publish_result
from pumpkin_private_region_guest import create_test_image, tail_bytes
from task_smoke import pump, send_bytes
from xos_app import tree_receipt

mark_struct = struct.Struct("<16sQQ32s")
header = struct.Struct("<4sHBBQ")
realm = bytes.fromhex("51704432" + "00" * 12)
blank = bytes(mark_struct.size)
frame_size = header.size + 2 * mark_struct.size
ready, read, publish, finish = range(1, 5)
result_codes = {publish_result.committed: 0, publish_result.conflict: 1,
                publish_result.unchanged: 2, publish_result.outcome_unknown: 3}
slow_snapshot_delay_ns = 7_000_000_000


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def sparse_snapshot(source, destination):
    with source.open("rb") as image, destination.open("xb") as snapshot:
        while chunk := image.read(1024 * 1024):
            if chunk.count(0) == len(chunk):
                snapshot.seek(len(chunk), os.SEEK_CUR)
            else:
                snapshot.write(chunk)
        snapshot.truncate(image.tell())
        snapshot.flush()
        os.fsync(snapshot.fileno())
    assert digest(source) == digest(destination), "snapshot did not capture identical disk bytes"


def snapshot_at_rev2(guest, source, destination, delay_ns):
    guest.qmp("stop")
    state = guest.qmp("query-status")
    assert state["status"] == "paused" and state["running"] is False, state
    start = time.monotonic_ns()
    if delay_ns:
        time.sleep(delay_ns / 1_000_000_000)
    sparse_snapshot(source, destination)
    paused_ns = time.monotonic_ns() - start
    assert paused_ns >= delay_ns
    guest.qmp("cont")
    return {"revision": 2, "qmp_status": state["status"], "injected_delay_ns": delay_ns,
            "paused_snapshot_wall_ns": paused_ns}


def packet(operation, result, sequence, value=blank):
    return header.pack(b"PKA1", 1, operation, result, sequence) + blank + value


def from_bytes(value):
    return None if value == blank else generation_mark(*mark_struct.unpack(value))


def receive(guest, offset, expected_sequence):
    deadline = time.monotonic() + 12
    while len(guest.output) < offset + frame_size:
        assert time.monotonic() < deadline, f"{guest.name}: no complete frame at sequence {expected_sequence}"
        pump(guest, 0.04)
    data = bytes(guest.output[offset:offset + frame_size])
    magic, version, operation, result, sequence = header.unpack_from(data)
    assert (magic, version, sequence) == (b"PKA1", 1, expected_sequence), (magic, version, sequence)
    return operation, result, data[header.size:header.size + mark_struct.size], data[-mark_struct.size:]


def binding(system, native_login=False):
    manifest = json.loads((system / "manifest.json").read_bytes())
    assert manifest.get("pumpkin_anchored_probe"), "dedicated anchored developer image required"
    assert not manifest.get("pumpkin_user_login"), "use the unrecorded private operator entry for this profile"
    assert manifest.get("pumpkin_native_login", False) == native_login, "native login profile mismatch"
    assert all(digest(root / name) == expected for name, expected in manifest["sources"].items()), "source mismatch"
    names = ("xos-install.iso", "user_files.image.elf", "user_supervisor.image.elf",
             "user_pumpkin_durable.image.elf", "user_p2_anchor_proxy.image.elf")
    if native_login:
        names += ("user_pumpkin_holder.image.elf",)
    artifacts = {name: digest(system / name) for name in names}
    assert all(value == manifest["artifacts"][name]["sha256"] for name, value in artifacts.items()), "artifact mismatch"
    return {"build_id": manifest["build_id"], "manifest_sha256": digest(system / "manifest.json"),
            "sdk_manifest_sha256": digest(system / "sdk/manifest.json"),
            "sdk_tree_sha256": tree_receipt(system / "sdk")[0], "artifacts": artifacts}


def boot(system, disk, output, phase, scenario, authority, stale_image, evidence, snapshot_delay_ns):
    guest = Guest(system / "xos-install.iso", phase, iso=True, work_disk=disk, log_dir=output)
    try:
        evidence["qemu_version"] = subprocess.check_output([guest.command[0], "--version"], text=True).splitlines()[0]
        events = evidence["events"]
        guest.expect(b"xos64> ", timeout=30)
        assert guest.qmp("query-status")["running"] is True
        start = len(guest.output)
        send_bytes(guest, b"run\r")
        preamble = packet(ready, 0, 0)[:header.size]
        guest.expect(preamble, start=start, timeout=30)
        offset = guest.output.index(preamble, start)
        current_sequence = 0
        while current_sequence < 20:
            operation, result, expected, value = receive(guest, offset, current_sequence)
            offset += frame_size
            if operation == ready:
                assert current_sequence == 0 and result == 0 and expected == blank and value == blank
                reply = packet(ready, scenario, current_sequence)
            elif operation == read:
                assert current_sequence > 0 and result == 0 and expected == blank and value == blank
                try:
                    selected = authority.read()
                    result = 0 if selected is not None else 1
                except generation_error:
                    selected, result = None, 2
                selected_bytes = blank if selected is None else mark_struct.pack(
                    selected.realm, selected.revision, selected.length, selected.checksum)
                events.append({"read": selected.revision if selected is not None else None})
                reply = packet(read, result, current_sequence, selected_bytes)
            elif operation == publish:
                assert scenario == 1 and current_sequence > 0 and result == 0
                candidate = from_bytes(value)
                assert candidate is not None
                published = authority.publish(from_bytes(expected), candidate)
                assert published == publish_result.committed
                events.append({"published": candidate.revision})
                if candidate.revision == 2:
                    # The slot was synced and verified before publication. While
                    # the guest awaits the ACK, stop its clock during the host copy.
                    evidence["snapshot_fence"] = snapshot_at_rev2(guest, disk, stale_image, snapshot_delay_ns)
                reply = packet(publish, result_codes[published], current_sequence)
            else:
                assert operation == finish and expected == blank and value == blank
                evidence["finish_code"] = result
                send_bytes(guest, packet(finish, 0, current_sequence))
                pump(guest, 0.15)
                guest.qmp("quit")
                assert guest.process.wait(timeout=10) == 0
                assert result == 1, f"{phase}: supervisor reported failure {result}"
                return
            send_bytes(guest, reply)
            current_sequence += 1
        raise AssertionError(f"{phase}: exceeded bounded exchange count")
    finally:
        guest.close()


def run(system, output, snapshot_delay_ns, native_login=False):
    output.mkdir(parents=True)
    report = {"status": "failed", "system": binding(system, native_login),
              "native_login": native_login, "runner_sha256": digest(Path(__file__)), "boots": {}}
    try:
        with tempfile.TemporaryDirectory(prefix="pumpkin_anchor_vm_") as directory:
            scratch = Path(directory)
            authority_root = scratch / "independent"
            authority_root.mkdir(mode=0o700)
            authority = generation_authority(authority_root, realm)
            authority.provision()
            disk = scratch / "current.img"
            old = scratch / "stale.img"
            cutoff = create_test_image(disk, "isolated")
            for phase, scenario, image in (("cycle", 1, disk), ("healthy", 2, disk), ("stale", 3, old)):
                events = []
                checks = {"events": events, "input_disk_sha256": digest(image)}
                report["boots"][phase] = checks
                boot(system, image, output, phase, scenario, authority, old, checks, snapshot_delay_ns)
                checks["output_disk_sha256"] = digest(image)
                checks["tail_sha256"] = hashlib.sha256(tail_bytes(image, cutoff)).hexdigest()
                checks["authority_revision"] = authority.read().revision
                assert checks["authority_revision"] == 3
                if phase == "cycle":
                    assert [event["published"] for event in events if "published" in event] == [1, 2, 3]
                    checks["offline_stale_copy_sha256"] = digest(old)
                else:
                    assert events == [{"read": 3}] and checks["input_disk_sha256"] == checks["output_disk_sha256"]
                checks["status"] = "passed"
                profile = "anchored native login" if native_login else "anchored"
                print(f"PASS {profile} Pumpkin {phase}", flush=True)
            assert report["boots"]["cycle"]["offline_stale_copy_sha256"] == report["boots"]["stale"]["input_disk_sha256"]
            assert report["boots"]["cycle"]["output_disk_sha256"] == report["boots"]["healthy"]["input_disk_sha256"]
        assert binding(system, native_login) == report["system"]
        report["status"] = "passed_subset"
    except BaseException as error:
        report["error"] = str(error)
        raise
    finally:
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")


def main():
    if not __debug__:
        raise RuntimeError("run the guest gate with assertions enabled")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--slow-snapshot", action="store_true", help="hold the paused revision-2 copy for seven seconds")
    parser.add_argument("--native-login", action="store_true", help="require the independent holder and sealed resource profile")
    arguments = parser.parse_args()
    run(arguments.system.resolve(), arguments.output.resolve(), slow_snapshot_delay_ns if arguments.slow_snapshot else 0,
        arguments.native_login)


if __name__ == "__main__":
    main()
