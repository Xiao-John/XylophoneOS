#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Serve one Pumpkin installation's independent generation on a local Linux socket."""

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import signal
import socket
import stat
import struct
import time

from pumpkin_generation_authority import generation_authority, generation_error, generation_mark, publish_result
from xypm_sdk_profile import digest_value, metadata_snapshot


developer_realm = bytes.fromhex("51704432" + "00" * 12)
mark_wire = struct.Struct("<16sQQ32s")
frame = struct.Struct("<4sHBB32s64s64s")
signature = (b"PGP1", 1)
read_operation, publish_operation = 1, 2
empty = bytes(mark_wire.size)
publish_results = (publish_result.committed, publish_result.conflict, publish_result.unchanged,
                   publish_result.outcome_unknown)


def deployment_realm(value):
    if not isinstance(value, str):
        raise ValueError("Select a nonzero 16-byte deployment realm")
    realm = bytes.fromhex(value)
    if len(realm) != 16 or value != realm.hex() or not any(realm) or realm == developer_realm:
        raise ValueError("Select a nonzero 16-byte deployment realm distinct from the developer realm")
    return realm


@dataclass(frozen=True)
class deployment_profile:
    realm: bytes
    system_manifest_sha256: str
    operator_uid: int
    provider_uid: int
    socket_path: Path
    named_resources: bool
    sha256: str
    provisioning: bool = False


def load_profile(path, expected_sha256):
    if expected_sha256 is None:
        raise ValueError("Supply the trusted deployment profile digest")
    value, actual = metadata_snapshot(path, expected_sha256)
    fields = {"format", "realm", "system_manifest_sha256", "operator_uid", "provider_uid",
              "provider_socket", "named_resources"}
    provisioning = value.get("format") == "xos-pumpkin-local-provider-v2"
    if (value.keys() != fields | ({"provisioning"} if provisioning else set()) or
            value["format"] not in ("xos-pumpkin-local-provider-v1", "xos-pumpkin-local-provider-v2") or
            type(value["named_resources"]) is not bool or
            (provisioning and (value["provisioning"] is not True or value["named_resources"] is not False))):
        raise ValueError("Invalid Pumpkin deployment profile")
    operator_uid, provider_uid = value["operator_uid"], value["provider_uid"]
    if (any(type(uid) is not int or not 0 < uid < 2**32 - 1 for uid in (operator_uid, provider_uid))
            or operator_uid == provider_uid):
        raise ValueError("The operator and provider require distinct non-root Linux UIDs")
    address = value["provider_socket"]
    if (not isinstance(address, str) or not address.startswith("/") or address != str(Path(address))
            or ".." in Path(address).parts or "\0" in address or address.endswith("/")):
        raise ValueError("Use a canonical absolute local provider socket path")
    return deployment_profile(deployment_realm(value["realm"]),
                              digest_value(value["system_manifest_sha256"], "deployment system manifest"),
                              operator_uid, provider_uid, Path(address), value["named_resources"], actual,
                              provisioning)


def require_uid(expected):
    if not hasattr(socket, "SO_PEERCRED") or os.geteuid() != expected:
        raise generation_error("The deployment role requires its configured Linux UID")


def peer_uid(connection):
    credentials = struct.Struct("=III")
    return credentials.unpack(connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED,
                                                    credentials.size))[1]


def encode_mark(mark):
    return empty if mark is None else mark_wire.pack(mark.realm, mark.revision, mark.length, mark.checksum)


def decode_mark(data, profile):
    if data == empty:
        return None
    mark = generation_mark(*mark_wire.unpack(data), named_resources=profile.named_resources,
                           provisioning=profile.provisioning)
    if mark.realm != profile.realm:
        raise generation_error("The provider mark is outside the installation realm")
    return mark


def receive(connection):
    deadline = time.monotonic() + 3
    data = bytearray(frame.size)
    with memoryview(data) as target:
        offset = 0
        while offset != len(target):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise generation_error("The provider exchange expired")
            connection.settimeout(remaining)
            count = connection.recv_into(target[offset:])
            if not count:
                raise generation_error("The provider exchange ended early")
            offset += count
    return frame.unpack(data)


class provider_client:
    def __init__(self, profile):
        require_uid(profile.operator_uid)
        self.profile = profile
        self.binding = bytes.fromhex(profile.sha256)
        self.named_resources = profile.named_resources
        self.provisioning = profile.provisioning

    def exchange(self, operation, expected=None, candidate=None):
        with socket.socket(socket.AF_UNIX) as connection:
            connection.settimeout(3)
            connection.connect(str(self.profile.socket_path))
            if peer_uid(connection) != self.profile.provider_uid:
                raise generation_error("The provider peer does not match the deployment profile")
            connection.sendall(frame.pack(*signature, operation, 0, self.binding,
                                          encode_mark(expected), encode_mark(candidate)))
            magic, version, kind, result, binding, previous, value = receive(connection)
        if ((magic, version) != signature or kind != operation or binding != self.binding or previous != empty):
            raise generation_error("Invalid reply from the independent provider")
        return result, value

    def read(self):
        try:
            result, value = self.exchange(read_operation)
            if result == 0 and value != empty:
                return decode_mark(value, self.profile)
            if result == 1 and value == empty:
                return None
        except (OSError, ValueError) as error:
            raise generation_error("The independent provider is unavailable") from error
        raise generation_error("The independent provider did not return a usable mark")

    def publish(self, expected, candidate):
        try:
            result, value = self.exchange(publish_operation, expected, candidate)
            if value == empty and result < len(publish_results):
                return publish_results[result]
        except (OSError, ValueError, generation_error):
            pass
        return publish_result.outcome_unknown


def handle(connection, profile, authority):
    if peer_uid(connection) != profile.operator_uid:
        return
    magic, version, operation, status, binding, previous, value = receive(connection)
    if (magic, version) != signature or status or binding != bytes.fromhex(profile.sha256):
        return
    if operation == read_operation and previous == value == empty:
        mark = authority.read()
        result, value = int(mark is None), encode_mark(mark)
    elif operation == publish_operation and value != empty:
        result = publish_results.index(authority.publish(decode_mark(previous, profile), decode_mark(value, profile)))
        value = empty
    else:
        return
    connection.settimeout(3)
    connection.sendall(frame.pack(*signature, operation, result, binding, empty, value))


def serve(profile, authority):
    authority.read()
    endpoint = profile.socket_path
    parent = endpoint.parent.lstat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != profile.provider_uid or parent.st_mode & 0o022:
        raise generation_error("The socket parent requires a private writer owned by the provider")
    with socket.socket(socket.AF_UNIX) as listener:
        listener.bind(str(endpoint))
        bound = endpoint.lstat()
        try:
            endpoint.chmod(0o660)
            listener.listen(4)
            while True:
                connection, _ = listener.accept()
                with connection:
                    try:
                        handle(connection, profile, authority)
                    except (OSError, ValueError, generation_error):
                        continue
        finally:
            try:
                current = endpoint.lstat()
            except FileNotFoundError:
                current = None
            if current is not None and (current.st_dev, current.st_ino) == (bound.st_dev, bound.st_ino):
                endpoint.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("provision", "serve"))
    for name in ("profile", "root"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--profile-sha256", required=True)
    args = parser.parse_args()
    try:
        profile = load_profile(args.profile, args.profile_sha256)
        require_uid(profile.provider_uid)
        authority = generation_authority(args.root, profile.realm, named_resources=profile.named_resources,
                                         provisioning=profile.provisioning)
        if args.operation == "provision":
            authority.provision()
        else:
            def stop(signum, frame_data):
                raise KeyboardInterrupt

            signal.signal(signal.SIGTERM, stop)
            serve(profile, authority)
    except KeyboardInterrupt:
        return
    except (OSError, ValueError, TypeError, generation_error):
        parser.exit(1, "Pumpkin generation provider could not complete the operation\n")


if __name__ == "__main__":
    main()
