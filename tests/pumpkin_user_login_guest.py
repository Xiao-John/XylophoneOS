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
from pumpkin_user_login import bind_system, credential_file_header, digest, file_magic, file_size, realm
from pumpkin_generation_authority import generation_authority, publish_result


def try_enroll(system, state, wallet):
    try:
        operator.operate(system, state, "enroll", wallet)
    except (operator.login_error, OSError):
        return
    raise RuntimeError("Faulted enrollment unexpectedly reported success")


def enrollment_failures(system, private, record):
    for fault in ("publication_unknown", "wallet_sync_failed"):
        state = private / fault
        wallet = private / (fault + "-credential")
        operator.prepare(state)
        authority = generation_authority(state / "authority", realm)
        if fault == "publication_unknown":
            publish = generation_authority.publish
            observed = []

            def publication(self, expected, candidate):
                result = publish(self, expected, candidate)
                if candidate.revision == 2:
                    observed.append(result)
                    return publish_result.outcome_unknown
                return result

            with patch.object(generation_authority, "publish", publication):
                try_enroll(system, state, wallet)
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
                try_enroll(system, state, wallet)
            assert sync_attempts == [True] and wallet.stat().st_size == file_size
        selected = authority.read()
        assert selected.revision == 2
        replacement = private / (fault + "-replacement")
        try_enroll(system, state, replacement)
        assert not replacement.exists() and authority.read() == selected
        record.append({"case": fault, "revision": 2, "replacement_created": False})
        print(f"PASS {fault} leaves the account and prevents duplicate issue", flush=True)


def run(system, output):
    output.mkdir(parents=True, exist_ok=False)
    ready = bind_system(system)
    tool = root / "scripts/pumpkin_user_login.py"
    report = {"status": "failed", "build_id": ready[0], "system_manifest_sha256": ready[1],
              "artifacts": ready[2], "entry_sha256": digest(tool), "runner_sha256": digest(Path(__file__)),
              "checks": []}
    try:
        with tempfile.TemporaryDirectory(prefix="pumpkin_wallet_") as directory:
            private = Path(directory)
            state, wallet = private / "installation", private / "credential"

            def invoke(command, label, expected=0, credential=None):
                args = [sys.executable, "-B", str(tool), command, "--system", str(system), "--state", str(state)]
                if credential is not None:
                    args += ["--credential-file", str(credential)]
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
            invoke("enroll", "durable issue to owner", credential=wallet)
            enrolled = authority.read()
            assert enrolled.revision == 2
            wallet_stat = wallet.stat()
            assert stat.S_IMODE(wallet_stat.st_mode) == 0o600 and wallet_stat.st_uid == os.geteuid()
            assert wallet_stat.st_size == file_size and wallet_stat.st_nlink == 1
            invoke("enroll", "duplicate enrollment refused", 1, credential=wallet)
            invoke("login", "fresh VM accepts the same credential and logs out", credential=wallet)
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
    options = parser.parse_args()
    run(options.system.resolve(), options.output.resolve())


if __name__ == "__main__":
    main()
