#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Real GNU descendants, persisted catalog selection and authority CAS/ACK faults.

The authority backend here is the developer generation_authority implementation.
Independent Linux UID isolation has a separate provider-v2 gate. Neither gate
claims physical arbitrary-power-loss qualification.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from boot_smoke import Guest
from pumpkin_generation_authority import generation_authority, publish_result
from pumpkin_anchored_guest import (binding, digest, sparse_snapshot, packet, realm, blank, frame_size,
                                   header, mark_struct, ready, read, publish, finish, result_codes)
from pumpkin_provisioning_guest import make_disk, mark
from task_smoke import pump, send_bytes
from work_disk import transfer


def programs(builds):
    assert len(builds) == 2
    files, roots, receipts = {}, [], []
    sdk, abi = None, None
    for build in builds:
        metadata = json.loads((build / "manifest.json").read_bytes())
        assert metadata["status"] == "built_not_run" and metadata["public_startup"] is True
        assert all(digest(Path(path)) == expected for path, expected in metadata["inputs"].items())
        fixture_source = ROOT / "tests/fixtures/pumpkin/catalog_descendants.c"
        source_inputs = [(path, expected) for path, expected in metadata["inputs"].items()
                         if Path(path).name == fixture_source.name]
        assert len(source_inputs) == 1 and source_inputs[0][1] == digest(fixture_source)
        if sdk is None:
            sdk, abi = metadata["sdk_binding"]["sdk_manifest_sha256"], metadata["native_abi"]
        assert metadata["sdk_binding"]["sdk_manifest_sha256"] == sdk and metadata["native_abi"] == abi
        for guest, record in metadata["files"].items():
            local = build / record["local"]
            assert digest(local) == record["sha256"]
            if guest in files:
                assert digest(files[guest]) == record["sha256"], "shared guest path has different content"
            else:
                files[guest] = local
        generation = metadata["generation"]
        local = build / generation["local"]
        assert digest(local) == generation["sha256"] and generation["guest"] not in files
        files[generation["guest"]] = local
        main = "/apps/" + metadata["name"] + "/main"
        assert main in files
        roots.append({"id": generation["id"], "sha256": generation["sha256"],
                      "manifest": generation["guest"], "main": main})
        receipts.append({"build_manifest_sha256": digest(build / "manifest.json"),
                         "generation": generation, "sdk_binding": metadata["sdk_binding"],
                         "native_sdk_binding": metadata["native_sdk_binding"], "native_abi": abi,
                         "guest_files": {path: item["sha256"] for path, item in metadata["files"].items()}})
    return files, {"format": "xos-pumpkin-catalog-fixture-v1", "sdk_sha256": sdk, "roots": roots}, receipts


def populate(disk, files):
    directories = set()
    for name in files:
        parent = Path(name).parent
        while str(parent) != "/":
            directories.add(str(parent))
            parent = parent.parent
    for directory in sorted(directories, key=lambda value: (value.count("/"), value)):
        transfer(disk, "mkdir", directory)
    for guest, local in sorted(files.items()):
        transfer(disk, "import", guest, local)


def receive(guest, offset, sequence):
    end = time.monotonic() + 95
    while len(guest.output) < offset + frame_size:
        assert time.monotonic() < end, f"{guest.name}: no frame at {sequence}"
        pump(guest, 0.04)
    data = bytes(guest.output[offset:offset + frame_size])
    magic, version, operation, result, received_sequence = header.unpack_from(data)
    assert (magic, version, received_sequence) == (b"PKA1", 1, sequence)
    return operation, result, data[header.size:header.size + mark_struct.size], data[-mark_struct.size:]


def boot(system, disk, output, name, scenario, authority, fault="none"):
    guest = Guest(system / "xos-install.iso", name, iso=True, work_disk=disk, log_dir=output)
    evidence = {"scenario": scenario, "fault": fault, "events": [], "status": "failed"}
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
                assert candidate is not None and previous == authority.read()
                injected = candidate.revision == 3 and fault != "none"
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
                if 100 <= result < 180:
                    evidence["spawn_stage"] = (result - 100) // 10
                    evidence["spawn_error_magnitude_capped_9"] = (result - 100) % 10
                send_bytes(guest, packet(finish, 0, sequence))
                pump(guest, 0.15)
                guest.qmp("quit")
                assert guest.process.wait(timeout=10) == 0
                assert result == 1, f"{name}: native supervisor failed, finish={result}"
                evidence["status"] = "passed"
                evidence["authority_revision"] = authority.read().revision
                return evidence
            send_bytes(guest, reply)
        raise AssertionError("bounded exchange count exhausted")
    except BaseException as error:
        evidence["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        guest.close()
        (output / f"{name}.json").write_text(json.dumps(evidence, indent=2) + "\n")


def run(system, builds, fixture, output):
    output.mkdir(parents=True, exist_ok=False)
    files, selected_fixture, receipts = programs(builds)
    assert json.loads(fixture.read_bytes()) == selected_fixture
    manifest = json.loads((system / "manifest.json").read_bytes())
    assert manifest.get("pumpkin_provisioning_store") == 1
    lease_profile = {"profile": "launch_acceptance", "duration_ns": 300_000_000_000}
    assert manifest.get("pumpkin_launch_storage_lease") == lease_profile
    assert manifest["pumpkin_catalog_fixture"]["input_sha256"] == digest(fixture)
    for key, value in selected_fixture.items():
        assert manifest["pumpkin_catalog_fixture"][key] == value
    report = {"status": "failed", "system": binding(system), "programs": receipts,
              "fixture_sha256": digest(fixture), "profile": "provisioning/private-region-v2/capsule-v3",
              "scope": "real GNU descendants and guest Files/IPC; developer authority CAS/ACK injection",
              "descendant_creation": "GNU posix_spawn parent to child to grandchild; parent first performs same-PID exec",
              "shared_gnu_fork": "ENOSYS; separate P1-K2 composition scope, not qualified here",
              "backing_storage_lease": lease_profile,
              "physical_power_loss": "not_qualified", "independent_provider_uid": "separate_gate",
              "test_control": "sys84 named pair; exact PPC1 HELLO/ACK; both peers checked against kernel identities",
              "sys81_backing_created_handles_required": 2,
              "sys81_supervisor_visible_owned_before_launch_required": 0,
              "sys81_visibility": "channel_get omits owner-only channels; the backing pair is recorded from create and authenticated by both peers",
              "cases": {}, "boot_count": 0}

    def run_boot(disk, name, scenario, authority, fault="none"):
        result = boot(system, disk, output, name, scenario, authority, fault)
        report["boot_count"] += 1
        return result

    def initialize(scratch):
        provider_root = scratch / "independent"
        provider_root.mkdir(mode=0o700)
        authority = generation_authority(provider_root, realm, provisioning=True)
        authority.provision()
        disk = scratch / "work.img"
        make_disk(disk)
        populate(disk, files)
        return authority, disk

    try:
        for fault in ("none", "rejected_cas", "committed_unknown", "uncommitted_unknown"):
            with tempfile.TemporaryDirectory(prefix="pumpkin_catalog_") as directory:
                scratch = Path(directory)
                authority, disk = initialize(scratch)
                first = run_boot(disk, fault + "_initial", 20, authority)
                assert first["authority_revision"] == 2
                old_disk = scratch / "old.img"
                sparse_snapshot(disk, old_disk)
                scenario = 22 if fault == "none" else 27 if fault == "rejected_cas" else 26
                mutation = run_boot(disk, fault + "_mutation", scenario, authority, fault)
                published = fault in ("none", "committed_unknown")
                expected = 3 if published else 2
                assert mutation["authority_revision"] == expected
                recovery = run_boot(disk, fault + "_cold_recovery", 23 if published else 21, authority)
                assert recovery["authority_revision"] == expected
                case = {"mutation": mutation["status"], "cold_recovery": recovery["status"],
                        "selected_generation": selected_fixture["roots"][1 if published else 0]["id"],
                        "selected_revision": expected, "actual_elf_launch": True}
                if published:
                    stale = run_boot(old_disk, fault + "_stale_disk", 3, authority)
                    case["stale_disk_denied"] = stale["status"] == "passed"
                report["cases"][fault] = case
        with tempfile.TemporaryDirectory(prefix="pumpkin_catalog_live_") as directory:
            authority, disk = initialize(Path(directory))
            for name, scenario in (("initial", 20), ("native_owner_before", 29), ("gnu_live_revoke", 24),
                                   ("native_owner_after", 29), ("cold_revoked", 25),
                                   ("revoke_last", 30), ("cold_all_revoked", 31)):
                report["cases"][name] = run_boot(disk, name, scenario, authority)["status"]
        with tempfile.TemporaryDirectory(prefix="pumpkin_catalog_unavailable_") as directory:
            authority, disk = initialize(Path(directory))
            run_boot(disk, "unavailable_initial", 20, authority)
            report["cases"]["authority_unavailable"] = run_boot(disk, "authority_unavailable", 28, authority)["status"]
        assert report["boot_count"] == 23 and binding(system) == report["system"]
        assert programs(builds)[1:] == (selected_fixture, receipts)
        report["status"] = "passed"
        report["checks"] = [
            "persisted active root restored and real GNU ELF launched",
            "rejected and unknown CAS select the exact complete old or new catalog",
            "stale work disk rejected against the independent revision",
            "GNU same-PID exec carries capsule v3 authority",
            "three actual parent/child/grandchild processes launch before explicit root revocation",
            "all three existing processes refuse launch after durable root revocation",
            "explicit native owner cannot launch another approved target after owner root revocation",
            "cold all-root revocation remains fail-closed",
            "three actual live descendants fail-closed when the daemon becomes unavailable",
        ]
        print("PASS real guest catalog: 23 boots, exact recovery, GNU descendants and live authority", flush=True)
    except BaseException as error:
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system-build", type=Path, required=True)
    parser.add_argument("--program-build", type=Path, action="append", required=True)
    parser.add_argument("--catalog-fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.system_build.resolve(), [path.resolve() for path in args.program_build],
        args.catalog_fixture.resolve(), args.output.resolve())
