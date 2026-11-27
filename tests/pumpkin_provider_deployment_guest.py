#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Boot Pumpkin with a real independent Linux user as the generation provider."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from pumpkin_generation_provider import deployment_realm, empty, frame, read_operation, signature
from pumpkin_user_login import bind_system, credential_file_header, digest, file_magic, file_size, sealed_login_image

OPERATOR, PROVIDER, HOLDER = 22101, 22102, 22103
GROUP = 22100


def actor(uid, *arguments, **options):
    options.setdefault("stdout", subprocess.DEVNULL)
    return subprocess.Popen(arguments, user=uid, group=GROUP, extra_groups=[], stderr=subprocess.DEVNULL, **options)


def private_owned(path, owner, mode):
    path.mkdir()
    os.chown(path, owner, GROUP)
    path.chmod(mode)


def run(system, output, provider_filesystem):
    binding = bind_system(system)
    manifest = json.loads((system / "manifest.json").read_bytes())
    realm = deployment_realm(manifest["pumpkin_deployment_realm"])
    named_resources = manifest.get("pumpkin_named_resource_store") is True
    if any(digest(ROOT / name) != expected for name, expected in manifest["sources"].items()):
        raise RuntimeError("deployment image differs from the guest gate sources")
    output.mkdir(parents=True)
    provider_tool = ROOT / "scripts/pumpkin_generation_provider.py"
    operator_tool = ROOT / "scripts/pumpkin_user_login.py"
    report = {"status": "failed", "build_id": binding[0], "system_manifest_sha256": binding[1], "artifacts": binding[2],
              "provider_entry_sha256": digest(provider_tool), "operator_entry_sha256": digest(operator_tool),
              "runner_sha256": digest(Path(__file__)), "installation_realm": realm.hex(),
              "named_resources": named_resources,
              "qemu": subprocess.check_output([os.environ.get("QEMU", "qemu-system-x86_64"), "--version"],
                                               text=True).splitlines()[0],
              "provider_filesystem": subprocess.check_output(
                  ["stat", "-f", "-c", "%T", provider_filesystem], text=True).strip(),
              "checks": []}
    try:
        with sealed_login_image(system / "xos-install.iso", binding[2]["xos-install.iso"]) as (image, descriptor):
            assert digest(image) == binding[2]["xos-install.iso"]
            try:
                os.pwrite(descriptor, b"X", 0)
            except PermissionError:
                pass
            else:
                raise AssertionError("the verified launch medium remained writable")
            report["checks"].append({"case": "verified launch medium is sealed"})
            print("PASS verified launch medium is sealed", flush=True)
        with (tempfile.TemporaryDirectory(prefix="pumpkin_generation_", dir=provider_filesystem) as persistent,
              tempfile.TemporaryDirectory(prefix="pumpkin_provider_") as temp):
            workspace = Path(temp)
            workspace.chmod(0o755)
            launcher = workspace / "operator"
            root = Path(persistent)
            sockets = workspace / "socket"
            private_owned(launcher, OPERATOR, 0o700)
            os.chown(root, PROVIDER, GROUP)
            root.chmod(0o700)
            private_owned(sockets, PROVIDER, 0o2750)
            state = launcher / "installation"
            wallet = launcher / "credential"
            endpoint = sockets / "generation.sock"
            contact = workspace / "host_profile.json"
            profile = {"format": "xos-pumpkin-local-provider-v1", "realm": realm.hex(),
                       "operator_uid": OPERATOR, "provider_uid": PROVIDER, "named_resources": named_resources,
                       "system_manifest_sha256": binding[1], "provider_socket": str(endpoint)}
            contact.write_text(json.dumps(profile) + "\n")
            contact.chmod(0o444)
            profile_digest = digest(contact)
            report["deployment_profile_sha256"] = profile_digest

            def result(label, process, expected, expected_output=None):
                try:
                    stdout, _ = process.communicate(timeout=100)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.communicate(timeout=10)
                if process.returncode != expected:
                    raise AssertionError(f"{label}: expected {expected}, received {process.returncode}")
                if expected_output is not None and stdout != (expected_output + "\n").encode():
                    raise AssertionError(f"{label}: unexpected operator result")
                check = {"case": label, "exit": process.returncode}
                if expected_output is not None:
                    check["result"] = expected_output
                report["checks"].append(check)
                print(f"PASS {label}", flush=True)

            def provide(action, user=PROVIDER, address=contact, sha=profile_digest):
                return actor(user, sys.executable, "-B", str(provider_tool), action,
                             "--root", str(root), "--profile", str(address), "--profile-sha256", sha)

            def execute(action, label, expected=0, credential=None, as_user=OPERATOR, profile_file=contact,
                        sha=profile_digest, include_profile=True, extra=(), expected_output=None):
                command = [sys.executable, "-B", str(operator_tool), action,
                           "--system", str(system), "--state", str(state)]
                if include_profile:
                    command.extend(("--deployment-profile", str(profile_file), "--deployment-profile-sha256", sha))
                if credential is not None:
                    command.extend(("--credential-file", str(credential)))
                command.extend(extra)
                stdout = subprocess.PIPE if expected_output is not None else subprocess.DEVNULL
                result(label, actor(as_user, *command, stdout=stdout), expected, expected_output)

            def start_provider():
                process = provide("serve")
                deadline = time.monotonic() + 8
                while not endpoint.exists():
                    if process.poll() is not None or time.monotonic() >= deadline:
                        if process.poll() is None:
                            process.kill()
                        process.wait(timeout=10)
                        raise AssertionError("independent provider could not start")
                    time.sleep(0.05)
                return process

            def stop_provider(process):
                process.terminate()
                process.wait(timeout=10)
                assert process.returncode == 0 and not endpoint.exists()

            record = root / realm.hex() / "generation"
            authority_record = struct.Struct("<8s16sQI32s")

            def revision(expected):
                data = record.read_bytes()
                assert hashlib.sha256(data[:-32]).digest() == data[-32:]
                assert authority_record.unpack(data[:-32])[1:3] == (realm, expected)
                return digest(record)

            execute("prepare", "deployment cannot fall back to a local provider", 1, include_profile=False)
            execute("prepare", "deployment rejects a missing provider", 1)
            result("provider cannot start before independent provisioning", provide("serve"), 1)
            result("operator cannot provision the generation provider", provide("provision", OPERATOR), 1)
            assert not state.exists() and not record.exists() and not endpoint.exists()
            result("separate Linux UID provisions an empty generation", provide("provision"), 0)
            record_zero = revision(0)
            result("operator cannot open the provider store directly",
                   actor(OPERATOR, sys.executable, "-c",
                         "import pathlib, sys; pathlib.Path(sys.argv[1]).read_bytes()", str(record)), 1)

            service = start_provider()
            try:
                script = ("import socket,sys\n"
                          "with socket.socket(socket.AF_UNIX) as conn:\n"
                          " conn.settimeout(3)\n"
                          " conn.connect(sys.argv[1])\n"
                          " try:\n"
                          "  conn.sendall(bytes.fromhex(sys.argv[2]))\n"
                          "  assert conn.recv(1) == b''\n"
                          " except (BrokenPipeError,ConnectionResetError):\n"
                          "  pass\n")
                read_frame = frame.pack(*signature, read_operation, 0, bytes.fromhex(profile_digest), empty, empty)
                result("provider refuses a different peer UID on the same socket group",
                       actor(HOLDER, sys.executable, "-B", "-c", script, str(endpoint), read_frame.hex()), 0)
                alternate = workspace / "alternate_provider.json"
                alternate.write_text(json.dumps(profile | {"provider_uid": HOLDER}) + "\n")
                alternate.chmod(0o444)
                execute("prepare", "launcher refuses a peer outside the pinned provider UID", 1,
                        profile_file=alternate, sha=digest(alternate))
                assert revision(0) == record_zero and not state.exists()
                execute("prepare", "operator installs against the independently prepared provider")
                assert not (state / "authority").exists()
                disk = state / "work.img"
                original = launcher / "original.img"
                shutil.copyfile(disk, original)
                os.chown(original, OPERATOR, GROUP)
                execute("provision-first", "non-operator cannot request first issuance", 1, wallet, as_user=HOLDER)
                assert revision(0) == record_zero and not wallet.exists()
                altered = workspace / "mismatched_profile.json"
                altered.write_text(json.dumps(profile | {"system_manifest_sha256": "0" * 64}) + "\n")
                altered.chmod(0o444)
                execute("provision-first", "different sealed image binding is rejected", 1, wallet,
                        profile_file=altered, sha=digest(altered))
                execute("provision-first", "profile digest mismatch is rejected", 1, wallet, sha="0" * 64)
                assert revision(0) == record_zero and not wallet.exists()
                execute("provision-first", "real guest issues the first credential", credential=wallet)
                enrolled = revision(2)
                details = wallet.stat()
                assert stat.S_IMODE(details.st_mode) == 0o600 and details.st_nlink == 1
                assert details.st_uid == OPERATOR and details.st_size == file_size
                with wallet.open("rb") as secret:
                    assert credential_file_header.unpack(secret.read(credential_file_header.size)) == (file_magic, realm, 1)
                failed = launcher / "unexpected-credential"
                execute("provision-first", "first issuance cannot be repeated", 1, failed)
                assert not failed.exists() and revision(2) == enrolled
            finally:
                stop_provider(service)

            execute("login", "normal login is denied while the provider is unavailable", 1, wallet)
            assert revision(2) == enrolled
            def reject_old_disk(old_disk, expected_revision, active_record, label):
                current = launcher / "current.img"
                old_disk_digest = digest(old_disk)
                disk.rename(current)
                old_disk.rename(disk)
                try:
                    execute("login", label, 1, wallet)
                    assert revision(expected_revision) == active_record
                finally:
                    disk.rename(old_disk)
                    current.rename(disk)
                assert digest(old_disk) == old_disk_digest
                report["checks"][-1]["revision"] = expected_revision

            def resource(action, label, expected_revision, *, generation=None, value=None,
                         expected=0, text=None):
                extra = ["--resource-name", "preview"]
                if generation is not None:
                    extra.extend(("--generation", str(generation)))
                if value is not None:
                    extra.extend(("--resource-value", str(value)))
                execute(action, label, expected, wallet if action == "read-named" else None,
                        extra=extra, expected_output=text)
                active = revision(expected_revision)
                report["checks"][-1]["revision"] = expected_revision
                return active

            service = start_provider()
            try:
                execute("login", "fresh VM and provider process confirm ordinary login", credential=wallet)
                assert revision(2) == enrolled
                reject_old_disk(original, 2, enrolled, "restoring the unprovisioned guest disk is refused")
                execute("login", "current disk still establishes a real ordinary session", credential=wallet)
                assert revision(2) == enrolled
                if named_resources:
                    denied = "Pumpkin named resource read denied"
                    assert resource("read-named", "owner starts without a named resource", 2, expected=4, text=denied) == enrolled
                    first = resource("publish-named", "registrar commits the first named resource", 3,
                                     generation=0, value=293, text="Pumpkin named resource generation 3 confirmed")
                    old_resource_disk = launcher / "published.img"
                    shutil.copyfile(disk, old_resource_disk)
                    os.chown(old_resource_disk, OPERATOR, GROUP)

                    service.kill()
                    assert service.wait(timeout=10) == -signal.SIGKILL
                    assert endpoint.is_socket() and revision(3) == first
                    report["checks"].append({"case": "committed resource survives provider process kill", "revision": 3})
                    print("PASS committed resource survives provider process kill", flush=True)
                    execute("login", "stale socket has no provider after process exit", 1, wallet)
                    assert revision(3) == first
                    endpoint.unlink()
                    service = start_provider()
                    assert resource("read-named", "restarted provider and fresh VM recover owner and data", 3,
                                    generation=3, text="Pumpkin named resource generation 3 value 293") == first

                    replaced = resource("publish-named", "registrar commits replacement under the same name", 4,
                                        generation=3, value=719, text="Pumpkin named resource generation 4 confirmed")
                    reject_old_disk(old_resource_disk, 4, replaced, "restoring the superseded resource disk is refused")
                    assert resource("read-named", "fresh VM rejects the old resource key", 4, generation=3,
                                    expected=4, text=denied) == replaced
                    assert resource("read-named", "restored current disk recovers the replacement", 4, generation=4,
                                    text="Pumpkin named resource generation 4 value 719") == replaced
                    assert resource("erase-named", "stale erase preserves the replacement", 4, generation=3,
                                    expected=5, text="Pumpkin named resource generation conflict") == replaced
                    erased = resource("erase-named", "registrar commits deletion of the current key", 5, generation=4,
                                      text="Pumpkin named resource generation 4 confirmed")
                    stop_provider(service)
                    service = start_provider()
                    assert resource("read-named", "fresh provider and VM recover the committed deletion", 5,
                                    expected=4, text=denied) == erased
                    execute("login", "ordinary credential survives named resource deletion", credential=wallet)
                    assert revision(5) == erased
                    final = wallet.stat()
                    assert (final.st_ino, final.st_size, final.st_mtime_ns) == (
                        details.st_ino, details.st_size, details.st_mtime_ns)
            finally:
                if service.poll() is None:
                    stop_provider(service)
        report["status"] = "passed_subset"
    finally:
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")


def main():
    if not __debug__ or not hasattr(socket, "SO_PEERCRED") or os.geteuid() != 0:
        raise RuntimeError("run with assertions as root inside a dedicated Linux test container")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--provider-filesystem", type=Path, required=True)
    args = parser.parse_args()
    run(args.system.resolve(strict=True), args.output.resolve(), args.provider_filesystem.resolve(strict=True))


if __name__ == "__main__":
    main()
