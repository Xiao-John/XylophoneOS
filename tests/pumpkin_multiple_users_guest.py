#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise two durable user credentials and one protected object in fresh guests."""

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
from pumpkin_user_login import (bind_system, broker_artifact, credential_file, credential_file_header,
                                digest, file_magic, named_profile, realm)
from run_qemu import qemu_command
from xos_app import tree_receipt


def legacy_binding(system, entry):
    assert entry.name == "pumpkin_user_login.py" and entry.parent.name == "scripts"
    workspace = entry.parent.parent
    manifest_path = system / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    assert manifest["pumpkin_user_login"] is True and manifest["pumpkin_named_resource_store"] is True
    assert "pumpkin_operator_protocol" not in manifest
    assert all(digest(workspace / name) == value for name, value in manifest["sources"].items())
    artifacts = {}
    for name in ("xos-install.iso", "user_files.image.elf", "user_supervisor.image.elf", "user_pumpkin_durable.image.elf",
                 "user_p2_anchor_proxy.image.elf", "user_pumpkin_holder.image.elf", broker_artifact, "sdk/manifest.json"):
        artifacts[name] = digest(system / name)
        assert artifacts[name] == manifest["artifacts"][name]["sha256"]
    return {"build_id": manifest["build_id"], "manifest_sha256": digest(manifest_path), "entry_sha256": digest(entry),
            "sdk_tree_sha256": tree_receipt(system / "sdk")[0], "artifacts": artifacts}


def identity(path):
    with credential_file(path, False) as (descriptor, _):
        tag, scope, number = credential_file_header.unpack(os.read(descriptor, credential_file_header.size))
        assert tag == file_magic and scope == realm and number > 0
        info = os.fstat(descriptor)
        return (scope, number), (info.st_ino, info.st_size, info.st_mtime_ns)


def run(system, output, legacy_system=None, legacy_entry=None):
    output.mkdir(parents=True, exist_ok=False)
    binding = bind_system(system)
    assert named_profile(system) and broker_artifact in binding[2]
    manifest = json.loads((system / "manifest.json").read_bytes())
    assert all(digest(root / name) == expected for name, expected in manifest["sources"].items())
    sdk_manifest = digest(system / "sdk/manifest.json")
    assert sdk_manifest == manifest["artifacts"]["sdk/manifest.json"]["sha256"]
    entry = root / "scripts/pumpkin_user_login.py"
    qemu = qemu_command(system / "xos-install.iso", iso=True)[0]
    report = {"status": "failed", "build_id": binding[0], "system_manifest_sha256": binding[1], "artifacts": binding[2],
              "sdk_manifest_sha256": sdk_manifest, "sdk_tree_sha256": tree_receipt(system / "sdk")[0],
              "entry_sha256": digest(entry), "runner_sha256": digest(Path(__file__)),
              "qemu_version": subprocess.check_output([qemu, "--version"], text=True).splitlines()[0], "checks": []}
    if legacy_system is not None:
        report["legacy"] = legacy_binding(legacy_system, legacy_entry)
    try:
        with tempfile.TemporaryDirectory(prefix="pumpkin_user_accounts_") as temporary:
            private = Path(temporary)
            state = private / "installation"
            wallets = {"alice": private / "alice.wallet", "carol": private / "carol.wallet"}
            authority = generation_authority(state / "authority", realm, named_resources=True)

            def invoke(command, case, revision, account=None, wallet=None, expected=0,
                       generation=None, value=None, answer=None, legacy=False):
                runner = legacy_entry if legacy else entry
                image = legacy_system if legacy else system
                args = [sys.executable, "-B", str(runner), command, "--system", str(image), "--state", str(state)]
                if account is not None:
                    args += ["--account", account]
                if wallet is not None:
                    args += ["--credential-file", str(wallet)]
                if command in ("read-named", "publish-named"):
                    args += ["--resource-name", "shared-name"]
                if generation is not None:
                    args += ["--generation", str(generation)]
                if value is not None:
                    args += ["--resource-value", str(value)]
                # The private VM pipe never goes to this runner. Only the
                # documented, secret-free status or synthetic value is compared.
                result = subprocess.run(args, timeout=60, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
                if result.returncode != expected or (answer is not None and result.stdout != answer + "\n"):
                    raise AssertionError(f"{case} returned an unexpected result (exit {result.returncode})")
                mark = authority.read()
                assert revision == (mark.revision if mark is not None else 0)
                report["checks"].append({"case": case, "revision": revision, "exit": expected})
                print(f"PASS {case}", flush=True)
                return mark

            seeded = legacy_system is not None
            invoke("prepare", "create one isolated developer installation", 0, legacy=seeded)
            alice = invoke("enroll", "issue Alice a real first credential", 2, wallet=wallets["alice"], legacy=seeded)
            assert invoke("login", "a fresh guest accepts the original Alice wallet and logs out", 2,
                          account="alice", wallet=wallets["alice"]) == alice
            both = invoke("enroll", "a fresh guest adds Carol to the existing account store", 3,
                          account="carol", wallet=wallets["carol"])
            issued = {name: identity(path) for name, path in wallets.items()}
            assert issued["alice"][0] != issued["carol"][0]
            duplicate = private / "duplicate.wallet"
            assert invoke("enroll", "duplicate account is refused before reserving a new wallet", 3,
                          account="carol", wallet=duplicate, expected=1) == both
            assert not duplicate.exists()
            assert invoke("login", "Carol authenticates with her unchanged wallet and logs out", 3,
                          account="carol", wallet=wallets["carol"]) == both
            assert invoke("login", "Alice wallet cannot be submitted for Carol", 3,
                          account="carol", wallet=wallets["alice"], expected=1) == both

            selected = invoke("publish-named", "the registrar publishes an object owned by Alice", 4,
                              account="alice", generation=0, value=860,
                              answer="Pumpkin named resource generation 4 confirmed")
            assert invoke("read-named", "Alice reads and her pending read is denied before expiry after logout", 4,
                          account="alice", wallet=wallets["alice"], generation=4,
                          answer="Pumpkin named resource generation 4 value 860") == selected
            denied = "Pumpkin named resource read denied"
            assert invoke("read-named", "authenticated Carol cannot read Alice's object", 4,
                          account="carol", wallet=wallets["carol"], generation=4, expected=4, answer=denied) == selected
            replaced = invoke("publish-named", "the registrar replaces the same name with a new Carol-owned object", 5,
                              account="carol", generation=4, value=318,
                              answer="Pumpkin named resource generation 5 confirmed")
            assert invoke("read-named", "Alice remains authenticated but is refused Carol's replacement", 5,
                          account="alice", wallet=wallets["alice"], generation=5, expected=4, answer=denied) == replaced
            assert invoke("read-named", "Carol as owner cannot reopen the previous generation", 5,
                          account="carol", wallet=wallets["carol"], generation=4, expected=4, answer=denied) == replaced
            assert invoke("read-named", "Carol reads her object and independently proves logout before expiry", 5,
                          account="carol", wallet=wallets["carol"], generation=5,
                          answer="Pumpkin named resource generation 5 value 318") == replaced

            alice_revoked = invoke("revoke", "revoke Alice alone in the durable store", 6, account="alice")
            assert invoke("login", "fresh VM refuses Alice's revoked wallet", 6,
                          account="alice", wallet=wallets["alice"], expected=3) == alice_revoked
            assert invoke("read-named", "Alice cannot establish a read session after revocation", 6,
                          account="alice", wallet=wallets["alice"], expected=3) == alice_revoked
            assert invoke("read-named", "Carol still reads her object after Alice is revoked", 6,
                          account="carol", wallet=wallets["carol"], generation=5,
                          answer="Pumpkin named resource generation 5 value 318") == alice_revoked
            carol_revoked = invoke("revoke", "revoke the remaining owner without replacing the object", 7, account="carol")
            assert invoke("read-named", "fresh VM rejects Carol's credential for her retained object", 7,
                          account="carol", wallet=wallets["carol"], generation=5, expected=3) == carol_revoked
            assert all(identity(path) == issued[name] for name, path in wallets.items())

            state = private / "second-installation"
            authority = generation_authority(state / "authority", realm, named_resources=True)
            first_wallet = private / "different-first.wallet"
            invoke("prepare", "create another blank installation", 0)
            first = invoke("enroll", "a new installation permits a first account other than Alice", 2,
                           account="initial-owner", wallet=first_wallet)
            assert invoke("login", "fresh VM restores without a preconfigured Alice", 2, account="initial-owner",
                          wallet=first_wallet) == first
        assert binding == bind_system(system) and tuple(output.iterdir()) == ()
        if legacy_system is not None:
            assert report["legacy"] == legacy_binding(legacy_system, legacy_entry)
        report["status"] = "passed_subset"
    finally:
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")


def main():
    if not __debug__:
        raise RuntimeError("run the guest gate with assertions enabled")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--legacy-system", type=Path)
    parser.add_argument("--legacy-operator", type=Path)
    args = parser.parse_args()
    if (args.legacy_system is None) != (args.legacy_operator is None):
        parser.error("supply the original system and its matching operator together")
    run(args.system.resolve(), args.output.resolve(), args.legacy_system.resolve() if args.legacy_system else None,
        args.legacy_operator.resolve() if args.legacy_operator else None)


if __name__ == "__main__":
    main()
