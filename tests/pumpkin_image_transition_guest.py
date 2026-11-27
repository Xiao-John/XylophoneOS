#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Rehearse a Pumpkin image switch on an isolated disk with a real provider."""

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
from tempfile import gettempdir, NamedTemporaryFile, TemporaryDirectory
import time

from pumpkin_provider_deployment_guest import GROUP, OPERATOR, PROVIDER, ROOT, actor, private_owned
from pumpkin_user_login import bind_system, deployment_marker, digest

OPERATOR_TOOL = ROOT / "scripts/pumpkin_user_login.py"
PROVIDER_TOOL = ROOT / "scripts/pumpkin_generation_provider.py"
GENERATION = struct.Struct("<8s16sQI32s")


def pin_system(system, expected):
    build_id, manifest_digest, artifacts = bind_system(system)
    metadata = (system / "manifest.json").read_bytes()
    if manifest_digest != expected or hashlib.sha256(metadata).hexdigest() != expected:
        raise ValueError("system manifest differs from the trusted digest")
    manifest = json.loads(metadata)
    realm = manifest.get("pumpkin_deployment_realm")
    if not isinstance(realm, str) or manifest.get("pumpkin_named_resource_store") is not True:
        raise ValueError("expected a deployed Pumpkin named resource image")
    return build_id, realm, artifacts


def replace_fixture_marker(state, sha256):
    # The isolated test supervisor emulates the authorized operator-side switch.
    with NamedTemporaryFile(dir=state, delete=False) as stream:
        temporary = Path(stream.name)
        os.fchown(stream.fileno(), OPERATOR, GROUP)
        stream.write(sha256.encode("ascii"))
        stream.flush()
        os.fsync(stream.fileno())
    try:
        temporary.replace(state / deployment_marker)
        directory = os.open(state, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def fixture(current, replacement, provider_root, workspace, report):
    private_owned(workspace / "operator", OPERATOR, 0o700)
    private_owned(workspace / "socket", PROVIDER, 0o2750)
    os.chown(provider_root, PROVIDER, GROUP)
    provider_root.chmod(0o700)
    state = workspace / "operator/installation"
    wallet = workspace / "operator/wallet"
    disk = state / "work.img"
    endpoint = workspace / "socket/generation.sock"
    realm = report["realm"]
    record = provider_root / realm / "generation"

    def profile(name, system_sha256):
        path = workspace / (name + ".json")
        data = {"format": "xos-pumpkin-local-provider-v1", "realm": realm,
                "operator_uid": OPERATOR, "provider_uid": PROVIDER, "named_resources": True,
                "provider_socket": str(endpoint), "system_manifest_sha256": system_sha256}
        path.write_text(json.dumps(data) + "\n")
        path.chmod(0o444)
        return ("--deployment-profile", str(path), "--deployment-profile-sha256", digest(path)), (
            "--root", str(provider_root), "--profile", str(path), "--profile-sha256", digest(path))

    old, old_provider = profile("current", report["current"]["manifest_sha256"])
    new, new_provider = profile("replacement", report["replacement"]["manifest_sha256"])

    def execute(label, uid, command, expected=0, stdout=None, stderr=None):
        result = subprocess.run(command, user=uid, group=GROUP, extra_groups=[], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=160)
        if (result.returncode != expected or (stdout is not None and result.stdout.strip() != stdout.encode())
                or (stderr is not None and stderr.encode() not in result.stderr)):
            raise AssertionError(f"{label}: exit {result.returncode}, {result.stdout!r}, {result.stderr!r}")
        report["checks"].append({"case": label, "exit": result.returncode})
        print("PASS", label, flush=True)

    def operate(system, profile_args, action, label, *args, expected=0, stdout=None, stderr=None):
        command = [sys.executable, "-B", str(OPERATOR_TOOL), action, "--system", str(system),
                   "--state", str(state), *profile_args, *args]
        execute(label, OPERATOR, command, expected, stdout, stderr)

    @contextmanager
    def running_provider(args):
        process = actor(PROVIDER, sys.executable, "-B", str(PROVIDER_TOOL), "serve", *args)
        try:
            deadline = time.monotonic() + 8
            while not endpoint.is_socket() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.05)
            if not endpoint.is_socket() or process.poll() is not None:
                raise AssertionError("generation provider did not expose its own socket")
            yield
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
            if process.returncode != 0 or endpoint.exists():
                raise AssertionError("generation provider did not shut down cleanly")

    def generation(number):
        data = record.read_bytes()
        if (hashlib.sha256(data[:-32]).digest() != data[-32:]
                or GENERATION.unpack(data[:-32])[1:3] != (bytes.fromhex(realm), number)):
            raise AssertionError("unexpected persisted generation")
        return hashlib.sha256(data).hexdigest()

    credential = ("--credential-file", str(wallet))
    name = ("--resource-name", "preview")
    execute("provider provisions independent root", PROVIDER,
            [sys.executable, "-B", str(PROVIDER_TOOL), "provision", *old_provider])
    with running_provider(old_provider):
        operate(current, old, "prepare", "operator prepares the real guest disk")
        operate(current, old, "provision-first", "current image enrolls the original wallet", *credential)
        generation(2)
        operate(current, old, "publish-named", "current image publishes an owned resource",
                *name, "--generation", "0", "--resource-value", "293",
                stdout="Pumpkin named resource generation 3 confirmed")
        original = generation(3)
        original_disk = digest(disk)
        original_wallet = digest(wallet)
        disk_inode = disk.stat().st_ino

    with running_provider(new_provider):
        operate(current, old, "login", "old operator binding rejects the new provider", *credential,
                expected=1, stderr="Private Pumpkin operation could not be confirmed")
        operate(replacement, new, "login", "candidate launcher rejects the old marker", *credential,
                expected=1, stderr="installation does not match the deployment profile")
        assert generation(3) == original and digest(disk) == original_disk

    replace_fixture_marker(state, new[-1])
    with running_provider(old_provider):
        operate(replacement, new, "login", "new operator binding rejects the old provider", *credential,
                expected=1, stderr="Private Pumpkin operation could not be confirmed")
        assert generation(3) == original and digest(disk) == original_disk

    with running_provider(new_provider):
        operate(replacement, new, "login", "replacement guest authenticates the original wallet",
                *credential, stdout="Pumpkin login confirmed and session logged out")
        operate(replacement, new, "read-named", "replacement guest reads the original resource",
                *credential, *name, "--generation", "3", stdout="Pumpkin named resource generation 3 value 293")
        assert generation(3) == original
        operate(replacement, new, "publish-named", "replacement guest commits a new generation",
                *name, "--generation", "3", "--resource-value", "719",
                stdout="Pumpkin named resource generation 4 confirmed")
        updated = generation(4)
        assert updated != original

    replace_fixture_marker(state, old[-1])
    with running_provider(old_provider):
        operate(current, old, "read-named", "current guest reopens the new generation after rollback",
                *credential, *name, "--generation", "4", stdout="Pumpkin named resource generation 4 value 719")
        assert generation(4) == updated and disk.stat().st_ino == disk_inode and digest(wallet) == original_wallet
    report["generations"] = {"before_switch": original, "after_update_and_rollback": updated}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("current", "replacement", "provider-filesystem", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("current-sha256", "replacement-sha256"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    if not __debug__ or not hasattr(socket, "SO_PEERCRED") or os.geteuid() != 0:
        raise RuntimeError("run with assertions as root inside a dedicated Linux test container")
    current, replacement = args.current.resolve(strict=True), args.replacement.resolve(strict=True)
    provider_filesystem = args.provider_filesystem.resolve(strict=True)
    current_id, realm, current_artifacts = pin_system(current, args.current_sha256)
    replacement_id, next_realm, replacement_artifacts = pin_system(replacement, args.replacement_sha256)
    if current_id == replacement_id or realm != next_realm:
        raise ValueError("expected distinct builds from one named resource installation realm")

    report = {"status": "failed", "realm": realm, "checks": [],
              "current": {"build_id": current_id, "manifest_sha256": args.current_sha256, "artifacts": current_artifacts},
              "replacement": {"build_id": replacement_id, "manifest_sha256": args.replacement_sha256,
                              "artifacts": replacement_artifacts},
              "tools": {path.name: digest(path) for path in (Path(__file__), PROVIDER_TOOL, OPERATOR_TOOL)},
              "storage": {role: subprocess.check_output(
                  ["findmnt", "--noheadings", "--target", folder, "--output", "FSTYPE"], text=True).strip()
                          for role, folder in (("provider", provider_filesystem), ("operator", gettempdir()))},
              "qemu": subprocess.check_output([os.environ.get("QEMU", "qemu-system-x86_64"), "--version"],
                                               text=True).splitlines()[0]}
    args.output.mkdir(parents=True, exist_ok=False)
    try:
        with (TemporaryDirectory(prefix="pumpkin_provider_", dir=provider_filesystem) as provider,
              TemporaryDirectory(prefix="pumpkin_operator_") as temporary):
            workspace = Path(temporary)
            workspace.chmod(0o755)
            fixture(current, replacement, Path(provider), workspace, report)
        report["status"] = "passed"
    finally:
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
