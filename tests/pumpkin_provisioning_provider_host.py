#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise provider v2 using real Linux process UIDs and SO_PEERCRED."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from pumpkin_generation_authority import generation_authority, generation_error, generation_mark, publish_result
from pumpkin_generation_provider import empty, frame, load_profile, peer_uid, provider_client, read_operation, signature

OPERATOR, PROVIDER, STRANGER, GROUP = 1001, 1002, 1003, 1000
REALM = bytes.fromhex("5a4419000102030405060708090a0b0c0d")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def actor(args):
    profile = load_profile(args.profile, args.profile_sha256)
    if args.action == "preflight":
        assert os.geteuid() == PROVIDER
        authority = generation_authority(args.root, profile.realm, provisioning=profile.provisioning,
                                         named_resources=profile.named_resources)
        with authority._parent() as descriptor:
            assert os.fstat(descriptor).st_uid == PROVIDER
        assert profile.provisioning and not profile.named_resources
    elif args.action == "private_record":
        try:
            descriptor = os.open(args.root / REALM.hex() / "generation", os.O_RDONLY)
        except PermissionError:
            pass
        else:
            os.close(descriptor)
            raise AssertionError("operator could read the provider's authority record")
    elif args.action == "raw_wrong_uid":
        with socket.socket(socket.AF_UNIX) as connection:
            connection.settimeout(3)
            connection.connect(str(profile.socket_path))
            assert peer_uid(connection) == PROVIDER
            try:
                connection.sendall(frame.pack(*signature, read_operation, 0,
                                               bytes.fromhex(profile.sha256), empty, empty))
                assert connection.recv(1) == b""
            except (BrokenPipeError, ConnectionResetError):
                pass
    elif args.action == "impostor":
        with socket.socket(socket.AF_UNIX) as listener:
            listener.bind(str(profile.socket_path))
            profile.socket_path.chmod(0o660)
            listener.settimeout(8)
            listener.listen(1)
            connection, _ = listener.accept()
            with connection:
                connection.settimeout(3)
                assert connection.recv(1) == b"", "client sent data to a wrong-UID provider"
    else:
        client = provider_client(profile)
        old = generation_mark(REALM, 1, 6272, hashlib.sha256(b"complete old provisioning unit").digest(),
                              provisioning=True)
        new = generation_mark(REALM, 2, 6340, hashlib.sha256(b"complete new provisioning unit").digest(),
                              provisioning=True)
        assert client.provisioning and not client.named_resources
        if args.action == "empty":
            assert client.read() is None
        elif args.action == "publish":
            assert client.publish(None, old) == publish_result.committed
            assert client.read() == old
            assert client.publish(old, new) == publish_result.committed
            assert client.read() == new
            assert client.publish(old, new) == publish_result.conflict
        elif args.action == "recover":
            assert client.read() == new
        elif args.action == "wrong_format":
            legacy = generation_mark(REALM, 3, 80, bytes(32))
            assert client.publish(new, legacy) == publish_result.outcome_unknown
            assert client.read() == new
        elif args.action == "wrong_provider":
            try:
                client.read()
            except generation_error:
                pass
            else:
                raise AssertionError("client trusted a wrong-UID provider")
        else:
            raise ValueError("unknown actor action")
    print(json.dumps({"action": args.action, "uid": os.geteuid(), "status": "passed"}), flush=True)


def run(output):
    if os.geteuid() != 0 or not hasattr(socket, "SO_PEERCRED"):
        raise RuntimeError("this gate needs real Linux root to launch distinct numeric UIDs")
    output.mkdir(parents=True, exist_ok=False)
    provider_tool = ROOT / "scripts/pumpkin_generation_provider.py"
    report = {
        "format": "xos-pumpkin-provisioning-provider-host-v1",
        "status": "failed",
        "scope": "real Linux process UIDs and Unix peer credentials; no guest power-loss claim",
        "kernel": os.uname().release,
        "operator_uid": OPERATOR, "provider_uid": PROVIDER, "stranger_uid": STRANGER,
        "realm": REALM.hex(),
        "sources": {str(path.relative_to(ROOT)): digest(path) for path in
                    (Path(__file__), provider_tool, ROOT / "scripts/pumpkin_generation_authority.py",
                     ROOT / "scripts/xypm_sdk_profile.py")},
        "checks": [],
    }
    processes = []
    try:
        with tempfile.TemporaryDirectory(prefix="pumpkin_provisioning_provider_") as temp:
            workspace = Path(temp)
            workspace.chmod(0o755)
            authority_root = workspace / "authority"
            authority_root.mkdir(mode=0o700)
            os.chown(authority_root, PROVIDER, GROUP)
            sockets = workspace / "socket"
            sockets.mkdir()
            os.chown(sockets, PROVIDER, GROUP)
            sockets.chmod(0o2750)
            endpoint = sockets / "generation.sock"
            value = {"format": "xos-pumpkin-local-provider-v2", "realm": REALM.hex(),
                     "system_manifest_sha256": hashlib.sha256(b"sealed test system").hexdigest(),
                     "operator_uid": OPERATOR, "provider_uid": PROVIDER,
                     "provider_socket": str(endpoint), "named_resources": False, "provisioning": True}
            profile_file = workspace / "profile.json"
            profile_file.write_text(json.dumps(value) + "\n")
            profile_file.chmod(0o444)
            anchor = digest(profile_file)
            report["profile_sha256"] = anchor

            def command(uid, argv, *, expected=0, label=None):
                completed = subprocess.run(argv, user=uid, group=GROUP, extra_groups=[], capture_output=True,
                                           text=True, timeout=15)
                record = {"case": label or argv[-1], "uid": uid, "exit": completed.returncode,
                          "stdout": completed.stdout, "stderr": completed.stderr}
                report["checks"].append(record)
                if (expected == 0 and completed.returncode != 0) or (expected != 0 and completed.returncode == 0):
                    raise AssertionError(json.dumps(record))
                print("PASS " + record["case"], flush=True)
                return completed

            def actor_command(action, contact=profile_file, sha=anchor):
                return [sys.executable, "-B", str(Path(__file__)), "actor", "--action", action,
                        "--profile", str(contact), "--profile-sha256", sha, "--root", str(authority_root)]

            def provider_command(operation, contact=profile_file, sha=anchor):
                return [sys.executable, "-B", str(provider_tool), operation, "--root", str(authority_root),
                        "--profile", str(contact), "--profile-sha256", sha]

            def start(argv, uid):
                process = subprocess.Popen(argv, user=uid, group=GROUP, extra_groups=[],
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                processes.append(process)
                return process

            def wait_endpoint(process, address=endpoint):
                until = time.monotonic() + 5
                while not address.exists():
                    if process.poll() is not None:
                        stdout, stderr = process.communicate()
                        raise AssertionError(f"provider exited {process.returncode}: {stdout}\n{stderr}")
                    if time.monotonic() >= until:
                        raise AssertionError("provider socket was not ready")
                    time.sleep(0.02)

            def stop(process, address=endpoint):
                process.terminate()
                stdout, stderr = process.communicate(timeout=10)
                assert process.returncode == 0, f"provider stop: {process.returncode}: {stdout}\n{stderr}"
                # The provider's normal SIGTERM handler removes its own bound inode.
                assert not address.exists(), "provider left its socket after clean shutdown"

            command(PROVIDER, actor_command("preflight"), label="strict v2 profile and private authority root")
            command(PROVIDER, provider_command("provision"), label="provider UID provisions v2 authority")
            command(OPERATOR, provider_command("provision"), expected=1,
                    label="operator UID cannot provision authority")
            command(OPERATOR, actor_command("private_record"), label="operator cannot read authority record")
            server = start(provider_command("serve"), PROVIDER)
            wait_endpoint(server)
            command(OPERATOR, actor_command("empty"), label="operator reads blank v2 authority")
            command(OPERATOR, actor_command("publish"), label="full v2 mark CAS and stale CAS rejection")
            command(OPERATOR, actor_command("wrong_format"), label="legacy mark rejected without changing v2 state")
            command(STRANGER, actor_command("raw_wrong_uid"), label="provider rejects actual wrong operator UID")
            stop(server)
            server = start(provider_command("serve"), PROVIDER)
            wait_endpoint(server)
            command(OPERATOR, actor_command("recover"), label="provider restart restores complete new mark")
            stop(server)

            legacy_file = workspace / "legacy-profile.json"
            legacy_value = dict(value)
            legacy_value.pop("provisioning")
            legacy_value["format"] = "xos-pumpkin-local-provider-v1"
            legacy_file.write_text(json.dumps(legacy_value) + "\n")
            legacy_file.chmod(0o444)
            command(PROVIDER, provider_command("serve", legacy_file, digest(legacy_file)), expected=1,
                    label="v1 reader cannot open v2 authority record")

            impostor_parent = workspace / "impostor"
            impostor_parent.mkdir()
            os.chown(impostor_parent, STRANGER, GROUP)
            impostor_parent.chmod(0o2750)
            impostor_endpoint = impostor_parent / "generation.sock"
            impostor_file = workspace / "impostor-profile.json"
            impostor_value = dict(value, provider_socket=str(impostor_endpoint))
            impostor_file.write_text(json.dumps(impostor_value) + "\n")
            impostor_file.chmod(0o444)
            impostor_sha = digest(impostor_file)
            impostor = start(actor_command("impostor", impostor_file, impostor_sha), STRANGER)
            wait_endpoint(impostor, impostor_endpoint)
            command(OPERATOR, actor_command("wrong_provider", impostor_file, impostor_sha),
                    label="operator authenticates real provider UID before sending profile or CAS")
            stdout, stderr = impostor.communicate(timeout=10)
            assert impostor.returncode == 0, f"impostor check: {stdout}\n{stderr}"
            report["checks"].append({"case": "wrong provider received zero protocol bytes", "uid": STRANGER,
                                     "exit": impostor.returncode, "stdout": stdout})
            report["status"] = "passed"
    except BaseException as error:
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate(timeout=5)
        (output / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    runner = sub.add_parser("run")
    runner.add_argument("--output", type=Path, required=True)
    participant = sub.add_parser("actor")
    participant.add_argument("--action", required=True)
    participant.add_argument("--profile", type=Path, required=True)
    participant.add_argument("--profile-sha256", required=True)
    participant.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    if args.operation == "run":
        run(args.output)
    else:
        actor(args)


if __name__ == "__main__":
    main()
