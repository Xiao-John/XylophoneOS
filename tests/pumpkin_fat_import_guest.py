#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify an anchored resource imported through a real FAT file pin and private operator boot."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from boot_smoke import Guest
from process_smoke import command, resources
from task_smoke import send_bytes

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "scripts"))
from pumpkin_generation_authority import generation_authority
from pumpkin_user_login import bind_system, broker_artifact, digest, named_profile, realm
from work_disk import transfer
from xos_app import tree_receipt


def work_tail(disk):
    with disk.open("rb") as stream:
        stream.seek(512 * 1024 * 1024)
        tail = stream.read()
        assert len(tail) == 19 * 512
    return hashlib.sha256(tail).hexdigest()


def bind(directory):
    manifest_file = directory / "manifest.json"
    manifest = json.loads(manifest_file.read_bytes())
    assert all(digest(root / name) == expected for name, expected in manifest["sources"].items())
    iso = digest(directory / "xos-install.iso")
    sdk = digest(directory / "sdk" / "manifest.json")
    assert iso == manifest["artifacts"]["xos-install.iso"]["sha256"]
    assert sdk == manifest["artifacts"]["sdk/manifest.json"]["sha256"]
    return {"build_id": manifest["build_id"], "manifest_sha256": digest(manifest_file), "iso_sha256": iso,
            "sdk_manifest_sha256": sdk, "sdk_tree_sha256": tree_receipt(directory / "sdk")[0]}


def replace_source(ordinary, disk, output):
    guest = Guest(ordinary / "xos-install.iso", "ordinary_fat", iso=True, work_disk=disk, log_dir=output)
    try:
        guest.expect(b"xos64> ", timeout=30)
        send_bytes(guest, b"run\r")
        guest.expect_supervisor(timeout=30)
        command(guest, "demo quiet", b"demo tasks")
        before = resources(guest)
        command(guest, "mv /input/next.bin /input/public.bin", b"[files] renamed /input/public.bin")
        assert resources(guest) == before
        guest.qmp("quit")
        assert guest.process.wait(timeout=8) == 0
        return before, subprocess.check_output([guest.command[0], "--version"], text=True).splitlines()[0]
    finally:
        guest.close()


def run(system, ordinary, output):
    output.mkdir(parents=True, exist_ok=False)
    assert named_profile(system) and broker_artifact in bind_system(system)[2]
    assert not named_profile(ordinary)
    entry = root / "scripts/pumpkin_user_login.py"
    report = {"status": "failed", "system": bind(system), "ordinary": bind(ordinary), "entry_sha256": digest(entry),
              "runner_sha256": digest(Path(__file__)), "checks": []}
    try:
        with tempfile.TemporaryDirectory(prefix="pumpkin_fat_wallet_") as directory:
            private = Path(directory)
            state, wallet = private / "installation", private / "credential"
            disk = state / "work.img"
            authority = generation_authority(state / "authority", realm, named_resources=True)

            def invoke(operation, case, revision, expect=0, generation=None, source=None, message=None):
                args = [sys.executable, "-B", str(entry), operation, "--system", str(system), "--state", str(state)]
                if operation in ("enroll", "read-named"):
                    args += ["--credential-file", str(wallet)]
                if operation in ("import-fat", "read-named"):
                    args += ["--resource-name", "artifact"]
                if generation is not None:
                    args += ["--generation", str(generation)]
                if source is not None:
                    args += ["--fat-source", source]
                process = subprocess.run(args, timeout=60, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
                if process.returncode != expect or (message is not None and process.stdout != message + "\n"):
                    raise AssertionError(f"{case} returned an unexpected result (exit {process.returncode})")
                mark = authority.read()
                assert (mark.revision if mark is not None else 0) == revision
                report["checks"].append({"case": case, "exit": expect, "revision": revision})
                print(f"PASS {case}", flush=True)
                return mark

            invoke("prepare", "create private test installation", 0)
            original = bytes([0, 255, 128, 10, *range(28)])
            replacement = bytes([255, 0, 192, 13, *range(40, 68)])
            assert len(original) == len(replacement) == 32
            transfer(disk, "mkdir", "/input")
            transfer(disk, "mkdir", "/input/directory")
            for name, data in (("public.bin", original), ("next.bin", replacement), ("empty.bin", b""),
                               ("large.bin", bytes(33))):
                source = private / name
                source.write_bytes(data)
                transfer(disk, "import", "/input/" + name, source)
            report["input_sha256"] = [hashlib.sha256(data).hexdigest() for data in (original, replacement)]

            enrolled = invoke("enroll", "durable account and held credential", 2)
            old_tail = work_tail(disk)
            current_source = "/input/public.bin"
            rejected = "Pumpkin FAT source could not supply a pinned file of 1 to 32 bytes"
            for suffix, source in (("missing", "/input/missing.bin"), ("directory", "/input/directory"),
                                   ("empty", "/input/empty.bin"), ("oversized", "/input/large.bin"),
                                   ("device", "/dev/null")):
                assert invoke("import-fat", f"{suffix} source rejected before publication", 2, 6, generation=0,
                              source=source, message=rejected) == enrolled
                assert work_tail(disk) == old_tail
            first = invoke("import-fat", "import exactly 32 binary bytes from the ordinary FAT file", 3,
                           generation=0, source=current_source, message="Pumpkin named resource generation 3 confirmed")
            first_value = f"Pumpkin named resource generation 3 bytes {original.hex()}"
            assert invoke("read-named", "fresh VM reads the complete privately owned snapshot and logs out", 3,
                          message=first_value) == first

            before_replace = work_tail(disk)
            reclaimed, qemu = replace_source(ordinary, disk, output)
            assert authority.read() == first and work_tail(disk) == before_replace
            exported = private / "after_rename.bin"
            transfer(disk, "export", current_source, exported)
            assert exported.read_bytes() == replacement
            report.update(qemu_version=qemu, ordinary_resources=reclaimed, private_tail_after_ordinary_rename=before_replace)
            report["checks"].append({"case": "ordinary xsh renames a different equal-length FAT file over the source",
                                     "exit": 0, "revision": 3})
            print("PASS ordinary FAT replacement preserves the privately anchored bytes", flush=True)

            assert invoke("read-named", "new VM still reads the original owner snapshot after ordinary replacement", 3,
                          generation=3, message=first_value) == first
            assert invoke("import-fat", "claiming initialization again cannot replace the existing snapshot", 3, 5,
                          generation=0, source=current_source, message="Pumpkin named resource generation conflict") == first
            second = invoke("import-fat", "trusted reimport publishes the new bytes under a fresh generation", 4,
                            generation=3, source=current_source, message="Pumpkin named resource generation 4 confirmed")
            assert invoke("read-named", "the old protected generation no longer reads", 4, 4, generation=3,
                          message="Pumpkin named resource read denied") == second
            assert invoke("read-named", "new VM reads the exact binary replacement through the authorized broker", 4,
                          generation=4, message=f"Pumpkin named resource generation 4 bytes {replacement.hex()}") == second
        assert report["system"] == bind(system) and report["ordinary"] == bind(ordinary)
        report["ordinary_serial_sha256"] = digest(output / "ordinary_fat_serial.log")
        report["status"] = "passed_subset"
    finally:
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")


def main():
    if not __debug__:
        raise RuntimeError("run the guest gate with assertions enabled")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", type=Path, required=True)
    parser.add_argument("--ordinary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.system.resolve(), args.ordinary.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
