#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check frozen GNU catalog bundles on a newly integrated native system.

This is two real guest boots, not a rerun or relabeling of the original 23-boot
qualification. The existing GNU runtime remains an immutable producer artifact.
"""
import argparse
import json
from pathlib import Path

from pumpkin_catalog_guest import (binding, boot, digest, generation_authority,
                                   make_disk, populate, programs, realm)


def runtime_binding(directory):
    manifest = json.loads((directory / "manifest.json").read_bytes())
    for name, expected in manifest["artifacts"].items():
        assert digest(directory / name) == expected, name
    return {"manifest_sha256": digest(directory / "manifest.json"),
            "native_abi": manifest["native_abi"], "artifacts": manifest["artifacts"],
            "producer_status": manifest["status"]}


def run(system, builds, fixture, runtime, output):
    output.mkdir(parents=True, exist_ok=False)
    files, selected, program_receipts = programs(builds)
    assert json.loads(fixture.read_bytes()) == selected
    manifest = json.loads((system / "manifest.json").read_bytes())
    lease = {"profile": "launch_acceptance", "duration_ns": 300_000_000_000}
    assert manifest["pumpkin_provisioning_store"] == 1
    assert manifest["pumpkin_launch_probe"] is True
    assert manifest["pumpkin_launch_storage_lease"] == lease
    assert manifest["pumpkin_catalog_fixture"]["input_sha256"] == digest(fixture)
    for key, value in selected.items():
        assert manifest["pumpkin_catalog_fixture"][key] == value
    runtime_receipt = runtime_binding(runtime)
    assert all(item["native_abi"] == runtime_receipt["native_abi"] for item in program_receipts)
    report = {"format": "xos-p1c-main-integration-guest-v1", "status": "failed",
              "qualification": "frozen GNU bundles on a new integrated native system",
              "system": binding(system), "programs": program_receipts,
              "runtime": runtime_receipt, "fixture_sha256": digest(fixture),
              "backing_storage_lease": lease, "boot_count": 0, "cases": {},
              "descendants": "same-PID exec followed by GNU posix_spawn parent/child/grandchild",
              "not_qualified": ["new K1 shared sleep API in the old libc", "shared GNU fork",
                                "physical arbitrary power loss", "the complete 23-boot matrix on this new image"]}
    try:
        authority_root = output / "independent"
        authority_root.mkdir(mode=0o700)
        authority = generation_authority(authority_root, realm, provisioning=True)
        authority.provision()
        disk = output / "work.img"
        make_disk(disk)
        populate(disk, files)
        for name, scenario, revision in (("initial", 20, 2), ("gnu_live_revoke", 24, 3)):
            result = boot(system, disk, output, name, scenario, authority)
            assert result["status"] == "passed" and result["authority_revision"] == revision
            report["cases"][name] = result
            report["boot_count"] += 1
        assert report["boot_count"] == 2
        assert binding(system) == report["system"]
        assert programs(builds)[1:] == (selected, program_receipts)
        assert runtime_binding(runtime) == runtime_receipt
        report["status"] = "passed"
        print("PASS C main integration: 2 real boots, frozen GNU launch and three-generation live revocation", flush=True)
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
    parser.add_argument("--runtime-build", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.system_build.resolve(), [path.resolve() for path in args.program_build],
        args.catalog_fixture.resolve(), args.runtime_build.resolve(), args.output.resolve())
