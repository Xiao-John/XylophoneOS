# SPDX-License-Identifier: Apache-2.0
"""Use a sealed wallet with the deployed Pumpkin guest and independent provider."""

import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from pumpkin_generation_provider import deployment_realm
from pumpkin_provider_deployment_guest import GROUP, OPERATOR, PROVIDER, private_owned
from pumpkin_user_login import bind_system, digest, immutable_memfd_seals, wipe


@contextmanager
def inherited(record, seals):
    descriptor = os.memfd_create("pumpkin-fixture-wallet", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    try:
        assert os.write(descriptor, record) == len(record)
        if seals:
            fcntl.fcntl(descriptor, fcntl.F_ADD_SEALS, seals)
        assert os.lseek(descriptor, 0, os.SEEK_CUR) == len(record)
        yield descriptor
        assert os.lseek(descriptor, 0, os.SEEK_CUR) == len(record)
    finally:
        os.close(descriptor)


def check(args):
    binding = bind_system(args.system)
    if binding[1] != args.system_manifest_sha256:
        raise ValueError("The deployed guest receipt differs")
    manifest = json.loads((args.system / "manifest.json").read_bytes())
    realm = deployment_realm(manifest["pumpkin_deployment_realm"])
    tool = ROOT / "scripts/pumpkin_user_login.py"
    provider = ROOT / "scripts/pumpkin_generation_provider.py"
    qemu = shutil.which(os.environ.get("QEMU", "qemu-system-x86_64"))
    if qemu is None:
        raise ValueError("QEMU is required")
    args.output.mkdir(parents=True)
    report = {"status": "failed", "system_build_id": binding[0], "system_manifest_sha256": binding[1],
              "iso_sha256": binding[2]["xos-install.iso"], "operator_entry_sha256": digest(tool),
              "provider_entry_sha256": digest(provider), "runner_sha256": digest(Path(__file__)),
              "roles": {"operator_uid": OPERATOR, "provider_uid": PROVIDER},
              "qemu": subprocess.check_output([qemu, "--version"], text=True).splitlines()[0],
              "checks": []}

    def checked(label, argv, uid, expected, *, error=None, text=None, fds=(), env=None):
        result = subprocess.run(argv, user=uid, group=GROUP, extra_groups=[], pass_fds=fds, env=env,
                                capture_output=True, timeout=125)
        assert result.returncode == expected, f"{label}: exit {result.returncode}"
        if error is not None:
            assert not result.stdout and result.stderr == (error + "\n").encode(), f"{label}: unexpected error"
        if text is not None:
            assert not result.stderr and result.stdout == (text + "\n").encode(), f"{label}: unexpected result"
        report["checks"].append({"case": label, "exit": expected})
        print("PASS", label, flush=True)

    try:
        with (TemporaryDirectory(prefix="pumpkin_sealed_provider_", dir=args.provider_filesystem) as persistent,
              TemporaryDirectory(prefix="pumpkin_sealed_operator_") as temporary):
            workspace, root = Path(temporary), Path(persistent)
            workspace.chmod(0o755)
            root.chmod(0o700)
            os.chown(root, PROVIDER, GROUP)
            launcher, sockets = workspace / "operator", workspace / "socket"
            private_owned(launcher, OPERATOR, 0o700)
            private_owned(sockets, PROVIDER, 0o2750)
            state, wallet = launcher / "installation", launcher / "credential"
            endpoint = sockets / "generation.sock"
            profile = workspace / "profile.json"
            profile.write_text(json.dumps({"format": "xos-pumpkin-local-provider-v1", "realm": realm.hex(),
                                           "system_manifest_sha256": binding[1], "named_resources":
                                           manifest.get("pumpkin_named_resource_store") is True,
                                           "operator_uid": OPERATOR, "provider_uid": PROVIDER,
                                           "provider_socket": str(endpoint)}) + "\n")
            profile.chmod(0o444)
            profile_sha = digest(profile)
            report["profile_sha256"] = profile_sha
            proof = launcher / "qemu-fd-check"
            wrapper = workspace / "checked-qemu"
            wrapper.write_text(f"#!{sys.executable}\n" + r"""import os, sys
identity = os.environ.pop("PUMPKIN_TEST_DESCRIPTOR")
for name in os.listdir("/proc/self/fd"):
    try:
        info = os.fstat(int(name))
    except OSError:
        continue
    if f"{info.st_dev}:{info.st_ino}" == identity:
        sys.exit(97)
with open(os.environ.pop("PUMPKIN_TEST_PROOF"), "x") as proof:
    proof.write("checked\n")
qemu = os.environ.pop("PUMPKIN_TEST_QEMU")
os.execv(qemu, [qemu, *sys.argv[1:]])
""")
            wrapper.chmod(0o755)

            def provider_command(action):
                return [sys.executable, "-B", str(provider), action, "--root", str(root), "--profile", str(profile),
                        "--profile-sha256", profile_sha]

            def operator_command(action, *extra):
                return [sys.executable, "-B", str(tool), action, "--system", str(args.system), "--state", str(state),
                        "--deployment-profile", str(profile), "--deployment-profile-sha256", profile_sha, *extra]

            def start():
                daemon = subprocess.Popen(provider_command("serve"), user=PROVIDER, group=GROUP, extra_groups=[],
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                deadline = time.monotonic() + 8
                while not endpoint.exists():
                    if daemon.poll() is not None or time.monotonic() >= deadline:
                        if daemon.poll() is None:
                            daemon.kill()
                            daemon.wait(timeout=10)
                        raise AssertionError("independent provider did not start")
                    time.sleep(0.05)
                return daemon

            def stop(daemon):
                daemon.terminate()
                assert daemon.wait(timeout=10) == 0 and not endpoint.exists()

            def submit(label, descriptor, expected, *, uid=OPERATOR, error=None, text=None, env=None):
                checked(label, operator_command("login", "--credential-fd", str(descriptor)), uid, expected,
                        fds=(descriptor,), error=error, text=text, env=env)

            checked("separate provider provisions the installation", provider_command("provision"), PROVIDER, 0)
            daemon = start()
            try:
                checked("operator prepares the bound installation", operator_command("prepare"), OPERATOR, 0)
                checked("real guest issues the initial private wallet",
                        operator_command("provision-first", "--credential-file", str(wallet)), OPERATOR, 0)
            finally:
                stop(daemon)
            record = root / realm.hex() / "generation"
            disk = state / "work.img"
            committed = {name: digest(path) for name, path in (("generation", record), ("guest_disk", disk),
                                                             ("wallet", wallet))}
            daemon = start()
            payload = bytearray(wallet.stat().st_size)
            try:
                with wallet.open("rb", buffering=0) as source:
                    assert source.readinto(payload) == len(payload)
                generic_error = "Private Pumpkin operation could not be confirmed; do not repeat enrollment automatically"
                with inherited(payload, immutable_memfd_seals()) as descriptor:
                    lock = os.open(state, os.O_RDONLY | os.O_DIRECTORY)
                    try:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        submit("same installation lock fences a sealed wallet", descriptor, 1, error=generic_error)
                    finally:
                        os.close(lock)
                    checked("sealed wallet cannot bypass trusted profile digest",
                            operator_command("login", "--credential-fd", str(descriptor),
                                             "--deployment-profile-sha256", "0" * 64),
                            OPERATOR, 1, fds=(descriptor,), error=generic_error)
                    info = os.fstat(descriptor)
                    env = dict(os.environ, QEMU=str(wrapper), PUMPKIN_TEST_QEMU=qemu,
                               PUMPKIN_TEST_DESCRIPTOR=f"{info.st_dev}:{info.st_ino}", PUMPKIN_TEST_PROOF=str(proof))
                    submit("sealed inherited wallet authenticates after provider restart", descriptor, 0, env=env,
                           text="Pumpkin login confirmed and session logged out")
                assert proof.read_text() == "checked\n"
                report["checks"].append({"case": "real QEMU did not inherit the wallet descriptor"})
                checked("separate provider cannot read the operator wallet",
                        [sys.executable, "-B", "-c", "from pathlib import Path; import sys; Path(sys.argv[1]).read_bytes()",
                         str(wallet)], PROVIDER, 1)
                with inherited(bytes(len(payload)), immutable_memfd_seals()) as descriptor:
                    submit("provider UID cannot invoke the operator login", descriptor, 1, uid=PROVIDER, error=generic_error)
                checked("enrollment rejects descriptor submission",
                        operator_command("enroll", "--credential-fd", "3"), OPERATOR, 2)
                checked("credential descriptor is scoped to ordinary login",
                        operator_command("read-resource", "--credential-fd", "3"), OPERATOR, 2)
                checked("ordinary login requires an explicit credential",
                        operator_command("login"), OPERATOR, 2)
                checked("file and descriptor submission are mutually exclusive",
                        operator_command("login", "--credential-file", str(wallet), "--credential-fd", "3"), OPERATOR, 2)
                with inherited(payload, fcntl.F_SEAL_SEAL) as descriptor:
                    submit("mutable inherited wallet rejected", descriptor, 1, error="The inherited credential is not sealed")
                with inherited(memoryview(payload)[:-1], immutable_memfd_seals()) as descriptor:
                    submit("truncated inherited wallet rejected", descriptor, 1, error="Invalid anonymous credential descriptor")
                with wallet.open("rb") as source:
                    submit("named regular file cannot be substituted for a sealed wallet", source.fileno(), 1,
                           error="Invalid anonymous credential descriptor")
                checked("unavailable inherited descriptor rejected before opening state",
                        operator_command("login", "--credential-fd", "3"), OPERATOR, 1,
                        error="Invalid inherited credential descriptor")
                payload[8] ^= 1
                with inherited(payload, immutable_memfd_seals()) as descriptor:
                    submit("wallet for a different installation rejected", descriptor, 1,
                           error="Invalid private credential record")
                payload[8] ^= 1
                payload[-1] ^= 1
                with inherited(payload, immutable_memfd_seals()) as descriptor:
                    submit("guest rejects a wrong key submitted through a sealed descriptor", descriptor, 3,
                           text="Pumpkin login denied")
                checked("original file input still authenticates and logs out",
                        operator_command("login", "--credential-file", str(wallet)), OPERATOR, 0)
                assert committed == {name: digest(path) for name, path in (("generation", record),
                                                                         ("guest_disk", disk), ("wallet", wallet))}
            finally:
                wipe(payload)
                stop(daemon)
        report.update(status="passed_subset", unchanged=sorted(committed))
    finally:
        (args.output / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


def main():
    if not __debug__ or not hasattr(socket, "SO_PEERCRED") or os.geteuid() != 0:
        raise SystemExit("Run on Linux as the fixture administrator, with Python assertions enabled")
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("system", "provider-filesystem", "output"):
        parser.add_argument("--" + name, type=lambda path: Path(path).resolve(), required=True)
    parser.add_argument("--system-manifest-sha256", required=True)
    check(parser.parse_args())


if __name__ == "__main__":
    main()
