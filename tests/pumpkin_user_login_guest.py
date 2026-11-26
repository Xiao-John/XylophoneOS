#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Replay the private operator entry across separate host processes and VMs."""

import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from unittest.mock import patch

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "scripts"))
import pumpkin_user_login as operator
from pumpkin_user_login import bind_system, broker_artifact, credential_file_header, digest, file_magic, file_size, realm
from pumpkin_generation_authority import generation_authority, publish_result


def try_first_provision(system, state, wallet):
    try:
        operator.operate(system, state, "provision-first", wallet)
    except (operator.login_error, OSError):
        return
    raise RuntimeError("Faulted first account provisioning unexpectedly reported success")


def enrollment_failures(system, private, record):
    for fault in ("genesis_unknown", "publication_unknown", "wallet_sync_failed"):
        state = private / fault
        wallet = private / (fault + "-credential")
        operator.prepare(state)
        authority = generation_authority(state / "authority", realm)
        revision = 1 if fault == "genesis_unknown" else 2
        if fault != "wallet_sync_failed":
            publish = generation_authority.publish
            observed = []

            def publication(self, expected, candidate):
                result = publish(self, expected, candidate)
                if candidate.revision == revision:
                    observed.append(result)
                    return publish_result.outcome_unknown
                return result

            with patch.object(generation_authority, "publish", publication):
                try_first_provision(system, state, wallet)
            assert observed == [publish_result.committed] and wallet.stat().st_size == 0
        else:
            sync = os.fsync
            save = operator.save_credential
            sync_attempts = []

            def wallet_write(descriptor, parent, identity, key):
                def sync_failure(target):
                    if target == descriptor:
                        sync_attempts.append(True)
                        raise OSError("injected credential synchronization failure")
                    return sync(target)

                with patch.object(os, "fsync", sync_failure):
                    return save(descriptor, parent, identity, key)

            with patch.object(operator, "save_credential", wallet_write):
                try_first_provision(system, state, wallet)
            assert sync_attempts == [True] and wallet.stat().st_size == file_size
        selected = authority.read()
        assert selected.revision == revision
        replacement = private / (fault + "-replacement")
        try_first_provision(system, state, replacement)
        assert not replacement.exists() and authority.read() == selected
        record.append({"case": fault, "revision": revision, "replacement_created": False})
        print(f"PASS {fault} preserves the published state and prevents repeated first provisioning", flush=True)


def destination_appears_after_preflight(system, state, wallet, authority):
    check = operator.check_new_destination
    marker = b"a newly reserved private file"

    def destination_check(path):
        check(path)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(marker)

    with patch.object(operator, "check_new_destination", destination_check):
        try:
            operator.operate(system, state, "provision-first", wallet)
        except FileExistsError:
            pass
        else:
            raise AssertionError("First provisioning accepted an occupied destination")
    assert wallet.read_bytes() == marker and authority.read() is None


def run(system, output, with_resource=False):
    output.mkdir(parents=True, exist_ok=False)
    ready = bind_system(system)
    if (broker_artifact in ready[2]) != with_resource:
        raise ValueError("replay and selected resource image do not match")
    manifest = json.loads((system / "manifest.json").read_bytes())
    if any(digest(root / name) != expected for name, expected in manifest["sources"].items()):
        raise ValueError("the selected image differs from the replay sources")
    tool = root / "scripts/pumpkin_user_login.py"
    report = {"status": "failed", "build_id": ready[0], "system_manifest_sha256": ready[1],
              "artifacts": ready[2], "entry_sha256": digest(tool), "runner_sha256": digest(Path(__file__)),
              "checks": []}
    try:
        with tempfile.TemporaryDirectory(prefix="pumpkin_wallet_") as directory:
            private = Path(directory)
            state, wallet = private / "installation", private / "credential"

            def invoke(command, label, expected=0, credential=None, account=None):
                args = [sys.executable, "-B", str(tool), command, "--system", str(system), "--state", str(state)]
                if credential is not None:
                    args += ["--credential-file", str(credential)]
                if account is not None:
                    args += ["--account", account]
                # Collect exit status only. No subprocess output or transport
                # is retained in the acceptance artifacts.
                result = subprocess.run(args, timeout=60, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if result.returncode != expected:
                    raise RuntimeError(f"{label} returned status {result.returncode}")
                report["checks"].append({"case": label, "exit": expected})
                print(f"PASS {label}", flush=True)

            invoke("prepare", "private installation")
            authority = generation_authority(state / "authority", realm)
            assert authority.read() is None
            collision = private / "existing"
            descriptor = os.open(collision, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(b"existing private file")
            invoke("enroll", "existing destination refused before publication", 1, credential=collision)
            assert collision.read_bytes() == b"existing private file" and authority.read() is None
            state.chmod(0o755)
            try:
                invoke("provision-first", "untrusted installation refused before first issue", 1, credential=wallet)
            finally:
                state.chmod(0o700)
            assert not wallet.exists() and authority.read() is None
            invoke("provision-first", "invalid first account request refused", 2, credential=wallet, account="/alice")
            assert not wallet.exists() and authority.read() is None
            destination_appears_after_preflight(system, state, private / "racing-destination", authority)
            report["checks"].append({"case": "destination occupied after preflight left genesis unpublished"})
            invoke("provision-first", "durable first issue to owner", credential=wallet)
            enrolled = authority.read()
            assert enrolled.revision == 2
            wallet_stat = wallet.stat()
            assert stat.S_IMODE(wallet_stat.st_mode) == 0o600 and wallet_stat.st_uid == os.geteuid()
            assert wallet_stat.st_size == file_size and wallet_stat.st_nlink == 1
            repeated = private / "repeated-first-account"
            invoke("provision-first", "duplicate first issue refused", 1, credential=repeated)
            invoke("provision-first", "first issue of another name refused after initialization", 1,
                   credential=repeated, account="another")
            assert not repeated.exists() and authority.read() == enrolled
            invoke("enroll", "duplicate enrollment refused", 1, credential=wallet)
            invoke("login", "fresh VM accepts the same credential and logs out", credential=wallet)
            if with_resource:
                invoke("read-resource", "first fresh VM reads owned resource and verifies logout", credential=wallet)
                assert authority.read() == enrolled
                invoke("read-resource", "second fresh VM reads resource of the same durable owner and verifies logout",
                       credential=wallet)
            assert authority.read() == enrolled
            assert wallet.stat().st_ino == wallet_stat.st_ino and wallet.stat().st_mtime_ns == wallet_stat.st_mtime_ns

            linked = private / "symlink"
            linked.symlink_to(wallet)
            invoke("login", "credential symlink refused", 1, credential=linked)
            linked.unlink()
            linked.hardlink_to(wallet)
            invoke("login", "multiply-linked credential refused", 1, credential=linked)
            linked.unlink()
            wallet.chmod(0o644)
            invoke("login", "public credential mode refused", 1, credential=wallet)
            wallet.chmod(0o600)

            wrong = private / "wrong"
            descriptor = os.open(wrong, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(credential_file_header.pack(file_magic, realm, 1) + bytes([1]) * 32)
            invoke("login", "wrong credential rejected by ordinary session", 3, credential=wrong)
            assert authority.read() == enrolled
            invoke("revoke", "durable registrar revocation")
            revoked = authority.read()
            assert revoked.revision == 3
            invoke("login", "fresh VM rejects the original revoked credential", 3, credential=wallet)
            if with_resource:
                invoke("read-resource", "fresh VM denies owned resource session after persistent revocation",
                       3, credential=wallet)
            assert authority.read() == revoked
            assert wallet.stat().st_ino == wallet_stat.st_ino and wallet.stat().st_mtime_ns == wallet_stat.st_mtime_ns
            enrollment_failures(system, private, report["checks"])
        assert bind_system(system) == ready
        assert tuple(output.iterdir()) == ()
        report["status"] = "passed_subset"
    finally:
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")


def main():
    if not __debug__:
        raise RuntimeError("run the guest gate with assertions enabled")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resource", action="store_true", help="verify the private resource command on fresh VMs")
    options = parser.parse_args()
    run(options.system.resolve(), options.output.resolve(), options.resource)


if __name__ == "__main__":
    main()
