# SPDX-License-Identifier: Apache-2.0
"""Test deployment binding checks with two retained Linux/QEMU build outputs."""

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts/pumpkin_user_login.py"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path):
    return json.loads(path.read_bytes())


def write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True) + "\n")
    return path, digest(path)


def state_snapshot(state):
    directory = state.stat()
    files = {}
    for path in state.iterdir():
        info = path.stat()
        files[path.name] = (info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, digest(path))
    return directory.st_ino, directory.st_mtime_ns, files


def stage_fixture(system, target, metadata):
    target.mkdir()
    for name in metadata["artifacts"]:
        origin = system / name
        if origin.is_file() and origin.parent == system:
            (target / name).symlink_to(origin)
    write_json(target / "manifest.json", metadata)


def run(system, replacement, other):
    current_meta, replacement_meta, other_meta = (
        read_json(path / "manifest.json") for path in (system, replacement, other))
    assert current_meta["build_id"] != replacement_meta["build_id"]
    assert current_meta["pumpkin_deployment_realm"] == replacement_meta["pumpkin_deployment_realm"]
    assert current_meta["pumpkin_deployment_realm"] != other_meta["pumpkin_deployment_realm"]
    assert current_meta["pumpkin_named_resource_store"] is True
    assert replacement_meta["pumpkin_named_resource_store"] is True
    assert not other_meta.get("pumpkin_named_resource_store")
    assert digest(system / "xos-install.iso") != digest(replacement / "xos-install.iso")

    uid = os.geteuid()
    provider_uid, alternate_uid = [value for value in (22101, 22102, 22103) if value != uid][:2]
    checks = []
    with tempfile.TemporaryDirectory(prefix="xos-pumpkin-image-") as scratch:
        root = Path(scratch)
        state = root / "state"
        state.mkdir(mode=0o700)

        def profile(name, image, **changes):
            meta = read_json(image / "manifest.json")
            data = {
                "format": "xos-pumpkin-local-provider-v1",
                "realm": meta["pumpkin_deployment_realm"],
                "system_manifest_sha256": digest(image / "manifest.json"),
                "operator_uid": uid,
                "provider_uid": provider_uid,
                "provider_socket": str(root / "unstarted.sock"),
                "named_resources": meta.get("pumpkin_named_resource_store") is True,
            }
            data.update(changes)
            return write_json(root / (name + ".json"), data)

        current_profile = profile("current", system)
        next_profile = profile("replacement", replacement)
        other_profile = profile("other", other)
        marker = state / "deployment.sha256"
        marker.write_text(current_profile[1])
        marker.chmod(0o600)
        disk = state / "work.img"
        disk.write_bytes(b"private work disk contents are outside this check\n")
        disk.chmod(0o600)

        def check(label, expected, *, selected=replacement, candidate=next_profile, current=current_profile):
            before = state_snapshot(state)
            process = subprocess.run(
                [sys.executable, "-B", str(LAUNCHER), "check-image-update",
                 "--state", str(state), "--system", str(system),
                 "--deployment-profile", str(current[0]), "--deployment-profile-sha256", current[1],
                 "--replacement-system", str(selected), "--replacement-deployment-profile", str(candidate[0]),
                 "--replacement-deployment-profile-sha256", candidate[1]],
                capture_output=True, text=True, timeout=15, check=False)
            assert process.returncode == int(expected is not None), (label, process.returncode, process.stderr)
            if expected is None:
                assert not process.stderr, (label, process.stderr)
                assert json.loads(process.stdout) == {
                    "status": "bindings_compatible",
                    "current_manifest_sha256": digest(system / "manifest.json"),
                    "replacement_manifest_sha256": digest(selected / "manifest.json"),
                }, (label, process.stdout)
            else:
                assert not process.stdout and expected in process.stderr, (label, process.stdout, process.stderr)
            assert state_snapshot(state) == before, label
            assert not (root / "unstarted.sock").exists(), label
            checks.append(label)

        check("distinct_same_domain_images", None)
        unconfirmed = "Pumpkin image update bindings could not be confirmed"
        check("current_profile_digest", unconfirmed, current=(current_profile[0], next_profile[1]))
        check("replacement_profile_digest", unconfirmed, candidate=(next_profile[0], current_profile[1]))
        check("replacement_manifest_binding", "System image does not match", candidate=current_profile)
        check("other_installation_realm", "changes the installation realm", selected=other, candidate=other_profile)
        roles = "changes the deployment roles or provider socket"
        check("replacement_operator_uid", roles, candidate=profile("operator", replacement, operator_uid=alternate_uid))
        check("replacement_provider_uid", roles, candidate=profile("provider", replacement, provider_uid=alternate_uid))
        check("replacement_provider_socket", roles,
              candidate=profile("socket", replacement, provider_socket=str(root / "alternate.sock")))
        check("diagnostic_requires_current_operator", unconfirmed,
              current=profile("wrong-user", system, operator_uid=alternate_uid))

        format_fixture = root / "format-fixture"
        stage_fixture(other, format_fixture,
                      {**other_meta, "pumpkin_deployment_realm": current_meta["pumpkin_deployment_realm"]})
        check("same_domain_different_storage_format", "changes the account or resource storage configuration",
              selected=format_fixture, candidate=profile("format", format_fixture))
        image_fixture = root / "image-fixture"
        stage_fixture(replacement, image_fixture, replacement_meta)
        (image_fixture / "xos-install.iso").unlink()
        (image_fixture / "xos-install.iso").symlink_to(other / "xos-install.iso")
        check("replacement_artifact_digest", "Login image differs", selected=image_fixture,
              candidate=profile("artifact", image_fixture))

        lock = os.open(state, os.O_RDONLY | os.O_DIRECTORY)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            check("active_installation_lock", "installation is busy")
        finally:
            os.close(lock)
        marker.write_text(next_profile[1])
        check("installation_bound_to_other_profile", "installation does not match")
        marker.unlink()
        check("missing_installation_binding", "missing its deployment binding")
        marker.write_text(current_profile[1])
        marker.chmod(0o600)
        disk.unlink()
        check("missing_work_disk", unconfirmed)
    return {
        "status": "passed",
        "builds": {label: {"build_id": meta["build_id"], "manifest_sha256": digest(path / "manifest.json")}
                   for label, path, meta in (("current", system, current_meta),
                                             ("replacement", replacement, replacement_meta),
                                             ("other_realm", other, other_meta))},
        "checks": checks,
        "operator_uid": uid,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("system", "replacement-system", "other-system"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if os.geteuid() == 0 or not hasattr(socket, "SO_PEERCRED"):
        parser.error("run this test as a non-root Linux operator")
    print(json.dumps(run(args.system.resolve(), args.replacement_system.resolve(), args.other_system.resolve()),
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
