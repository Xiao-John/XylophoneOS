#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify named resources through the private operator command in fresh QEMU processes."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "scripts"))
from pumpkin_generation_authority import generation_authority
from pumpkin_user_login import bind_system, broker_artifact, digest, named_profile, realm
from run_qemu import qemu_command


def run(system, output):
    output.mkdir(parents=True, exist_ok=False)
    binding = bind_system(system)
    assert named_profile(system) and broker_artifact in binding[2]
    manifest = json.loads((system / "manifest.json").read_bytes())
    assert all(digest(root / name) == expected for name, expected in manifest["sources"].items())
    entry = root / "scripts/pumpkin_user_login.py"
    qemu = qemu_command(system / "xos-install.iso", iso=True)[0]
    report = {"status": "failed", "build_id": binding[0], "system_manifest_sha256": binding[1],
              "artifacts": binding[2], "entry_sha256": digest(entry), "runner_sha256": digest(Path(__file__)),
              "qemu_version": subprocess.check_output([qemu, "--version"], text=True).splitlines()[0], "checks": []}
    try:
        with tempfile.TemporaryDirectory(prefix="pumpkin_named_wallet_") as directory:
            private = Path(directory)
            state, wallet = private / "installation", private / "credential"
            authority = generation_authority(state / "authority", realm, named_resources=True)

            def invoke(command, label, revision, expected_status=0, generation=None, value=None, text=None,
                       name="preview"):
                args = [sys.executable, "-B", str(entry), command, "--system", str(system), "--state", str(state)]
                if command in ("enroll", "login", "read-named"):
                    args += ["--credential-file", str(wallet)]
                if command.endswith("-named"):
                    args += ["--resource-name", name]
                if generation is not None:
                    args += ["--generation", str(generation)]
                if value is not None:
                    args += ["--resource-value", str(value)]
                expected = f"{text}\n" if text is not None else None
                # Only the documented, secret-free operator result is compared.
                # The private transport and credentials are never recorded.
                result = subprocess.run(args, timeout=60, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                        text=True)
                if result.returncode != expected_status or (expected is not None and result.stdout != expected):
                    raise RuntimeError(f"{label} returned an unexpected result (exit {result.returncode})")
                selected = authority.read()
                assert revision == (selected.revision if selected is not None else 0)
                check = {"case": label, "exit": expected_status, "revision": revision}
                if text is not None:
                    check["result"] = text
                report["checks"].append(check)
                print(f"PASS {label}", flush=True)
                return selected

            invoke("prepare", "typed private installation", 0)
            enrolled = invoke("enroll", "issue a persistent account credential", 2)
            credential = os.stat(wallet, follow_symlinks=False)
            denied = "Pumpkin named resource read denied"
            conflict = "Pumpkin named resource generation conflict"
            assert invoke("read-named", "working credential sees no object before publication", 2, 4,
                          text=denied) == enrolled
            first = invoke("publish-named", "the trusted registrar assigns the new object to the enrolled owner", 3,
                           generation=0, value=293, text="Pumpkin named resource generation 3 confirmed")
            assert invoke("read-named", "fresh VM reads the current object and rejects a pending read after logout", 3,
                          text="Pumpkin named resource generation 3 value 293") == first
            assert invoke("read-named", "fresh VM recovers the same credential, fixed generation and data", 3,
                          generation=3, text="Pumpkin named resource generation 3 value 293") == first
            assert invoke("read-named", "a valid session cannot read a different logical name", 3, 4,
                          text=denied, name="other") == first

            replaced = invoke("publish-named", "the registrar replaces the same name with a new object key", 4,
                              generation=3, value=719, text="Pumpkin named resource generation 4 confirmed")
            assert invoke("read-named", "a fresh valid session cannot read the old generation", 4, 4, generation=3,
                          text=denied) == replaced
            assert invoke("read-named", "fresh VM reads replacement data and rejects a pending read after logout", 4,
                          text="Pumpkin named resource generation 4 value 719") == replaced
            assert invoke("erase-named", "stale erase cannot remove the replacement", 4, 5, generation=3,
                          text=conflict) == replaced
            erased = invoke("erase-named", "the registrar invalidates the exact replacement generation", 5,
                            generation=4, text="Pumpkin named resource generation 4 confirmed")
            assert invoke("read-named", "fresh VM rejects the deleted key", 5, 4, generation=4, text=denied) == erased
            assert invoke("read-named", "fresh VM recovers absence by logical name", 5, 4, text=denied) == erased

            current = invoke("publish-named", "recreating the logical name does not reuse the erased key", 6,
                             generation=0, value=991, text="Pumpkin named resource generation 6 confirmed")
            assert invoke("read-named", "the original owner reads the recreated object", 6, generation=6,
                          text="Pumpkin named resource generation 6 value 991") == current
            revoked = invoke("revoke", "durable registrar revocation leaves a current object with a revoked owner", 7)
            assert invoke("read-named", "fresh VM refuses the revoked credential for the current object", 7, 3,
                          generation=6, text="Pumpkin login denied") == revoked
            assert invoke("login", "fresh VM refuses the same credential without a resource request", 7, 3,
                          text="Pumpkin login denied") == revoked
            final = os.stat(wallet, follow_symlinks=False)
            assert (final.st_ino, final.st_size, final.st_mtime_ns) == (
                credential.st_ino, credential.st_size, credential.st_mtime_ns)
        assert bind_system(system) == binding and tuple(output.iterdir()) == ()
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
