#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Manage private Pumpkin login and developer resources in a disposable VM."""

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import socket
import stat
import struct
import subprocess
import tempfile
import time

from make_work_disk import create_fat32
from pumpkin_generation_authority import generation_authority, generation_error, generation_mark, publish_result
from run_qemu import qemu_command


realm = bytes.fromhex("51704432" + "00" * 12)
header = struct.Struct("<4sHBBQ")
mark_layout = struct.Struct("<16sQQ32s")
credential_file_header = struct.Struct("<8s16sQ")
file_magic = b"PUMKEY\0\1"
secret_size = 32
file_size = credential_file_header.size + secret_size
frame_size = header.size + 2 * mark_layout.size
empty_mark = bytes(mark_layout.size)
identity_offset = header.size
secret_offset = identity_offset + 24
padding_offset = secret_offset + secret_size
ready, read, publish, finish = range(1, 5)
issue, submit = range(1, 3)
scenarios = {"enroll": 4, "login": 5, "revoke": 6, "read-resource": 7}
named_operations = {"read-named": 1, "publish-named": 2, "erase-named": 3}
scenarios.update({"read-named": 9, "publish-named": 10, "erase-named": 11})
submission_commands = ("login", "read-resource", "read-named")
credential_operations = {"enroll": issue, **dict.fromkeys(submission_commands, submit)}
named_layout = struct.Struct("<QIB3x16s")
named_empty = bytes(frame_size - header.size)
broker_artifact = "user_p2_sealed.image.elf"
resource_errors = {
    29: "Pumpkin resource session did not complete",
    32: "Pumpkin sealed broker could not start",
    33: "Pumpkin sealed broker startup was not confirmed",
    34: "Pumpkin sealed broker was not admitted",
    35: "Pumpkin sealed broker did not close cleanly",
}
directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


class login_error(RuntimeError):
    """Operator-facing errors contain stage descriptions and no transport bytes."""


def require(condition, message):
    if not condition:
        raise login_error(message)


def wipe(buffer):
    buffer[:] = bytes(len(buffer))


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@contextmanager
def private_directory(path):
    descriptor = os.open(path, directory_flags)
    try:
        info = os.fstat(descriptor)
        require(info.st_uid == os.geteuid() and info.st_mode & 0o077 == 0,
                "Select a directory accessible only to its owner")
        yield descriptor
    finally:
        os.close(descriptor)


@contextmanager
def credential_file(path, create):
    """The validated descriptor is the same one used for every secret byte."""
    with private_directory(path.parent) as parent:
        flags = os.O_NOFOLLOW | os.O_NONBLOCK
        flags |= (os.O_WRONLY | os.O_CREAT | os.O_EXCL) if create else os.O_RDONLY
        descriptor = os.open(path.name, flags, 0o600, dir_fd=parent)
        try:
            info = os.fstat(descriptor)
            require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600 and
                    info.st_uid == os.geteuid() and info.st_nlink == 1 and
                    info.st_size == (0 if create else file_size), "Invalid private credential file")
            yield descriptor, parent
        finally:
            os.close(descriptor)


def read_credential(descriptor, record):
    with memoryview(record) as data:
        offset = 0
        while offset < len(data):
            count = os.readv(descriptor, [data[offset:]])
            require(count != 0, "Incomplete private credential file")
            offset += count
    tag, scope, number = credential_file_header.unpack_from(record)
    require(tag == file_magic and scope == realm and number > 0 and any(memoryview(record)[-secret_size:]),
            "Invalid private credential record")


def save_credential(descriptor, parent, identity, key):
    scope, number = struct.unpack("<16sQ", identity)
    require(scope == realm and number > 0 and any(key), "Invalid issued credential")
    record = bytearray(file_size)
    try:
        credential_file_header.pack_into(record, 0, file_magic, scope, number)
        record[-secret_size:] = key
        with memoryview(record) as data:
            offset = 0
            while offset < len(data):
                count = os.write(descriptor, data[offset:])
                require(count != 0, "Credential file write did not complete")
                offset += count
        os.fsync(descriptor)
        os.fsync(parent)
    finally:
        wipe(record)


def install_disk(path):
    public_size = 512 * 1024 * 1024
    public_sectors = public_size // 512
    create_fat32(path, 512)
    descriptor = bytearray(512)
    struct.pack_into("<8sIIQ", descriptor, 0, b"XOSPRIV1", 1, 9, public_sectors)
    with path.open("r+b") as disk:
        disk.truncate(public_size + 19 * 512)
        disk.seek(public_size)
        disk.write(descriptor)
        for sector in (0, 6):
            disk.seek(sector * 512 + 32)
            disk.write(struct.pack("<I", public_sectors))
        disk.flush()
        os.fsync(disk.fileno())


def prepare(state, named_resources=False):
    state.mkdir(mode=0o700)
    with private_directory(state) as descriptor:
        authority_path = state / "authority"
        authority_path.mkdir(mode=0o700)
        generation_authority(authority_path, realm, named_resources=named_resources).provision()
        install_disk(state / "work.img")
        os.fsync(descriptor)


def bind_system(system):
    manifest = system / "manifest.json"
    checked = json.loads(manifest.read_bytes())
    require(checked.get("pumpkin_user_login") is True, "Select the private operator login image")
    names = ("xos-install.iso", "user_files.image.elf", "user_supervisor.image.elf",
             "user_pumpkin_durable.image.elf", "user_p2_anchor_proxy.image.elf", "user_pumpkin_holder.image.elf")
    if checked.get("pumpkin_user_resource") is True:
        names += (broker_artifact,)
    artifacts = {name: digest(system / name) for name in names}
    require(all(checked["artifacts"][name]["sha256"] == value for name, value in artifacts.items()),
            "Login image differs from its build receipt")
    return checked["build_id"], digest(manifest), artifacts


class private_vm:
    """Unlike the general test console, this pipe never accumulates a recording."""

    def __init__(self, command):
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, bufsize=0, close_fds=True)
        self.reader = selectors.DefaultSelector()
        self.reader.register(self.process.stdout, selectors.EVENT_READ)

    def send(self, frame):
        with memoryview(frame) as data:
            for index in range(len(data)):
                require(os.write(self.process.stdin.fileno(), data[index:index + 1]) == 1,
                        "Private device write did not complete")
                time.sleep(0.003)

    def receive(self, buffer, deadline):
        with memoryview(buffer) as output:
            offset = 0
            while offset != len(output):
                left = deadline - time.monotonic()
                require(left > 0 and self.reader.select(left), "Private device reply timed out")
                count = os.readv(self.process.stdout.fileno(), [output[offset:]])
                require(count != 0, "Private guest disconnected")
                offset += count

    def scan_boot(self, marker):
        end = time.monotonic() + 30
        window = bytearray(len(marker))
        value = bytearray(1)
        for _ in range(65536):
            self.receive(value, end)
            window[:-1] = window[1:]
            window[-1] = value[0]
            if window == marker:
                return
        raise login_error("Private login readiness marker was not received")

    def close(self):
        self.reader.close()
        try:
            if self.process.poll() is None:
                self.process.terminate()
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        finally:
            self.process.stdin.close()
            self.process.stdout.close()


def quit_qmp(path):
    def reply(stream, key):
        for _ in range(16):
            entry = json.loads(stream.readline(65536))
            if key in entry:
                return
        raise login_error("Private guest monitor did not complete shutdown")

    with socket.socket(socket.AF_UNIX) as monitor:
        monitor.settimeout(8)
        monitor.connect(str(path))
        with monitor.makefile("rwb", buffering=0) as stream:
            reply(stream, "QMP")
            stream.write(b'{"execute":"qmp_capabilities"}\n')
            reply(stream, "return")
            stream.write(b'{"execute":"quit"}\n')
            reply(stream, "return")


def generation_packet(operation, status, sequence, value=empty_mark):
    return header.pack(b"PKA1", 1, operation, status, sequence) + empty_mark + value


def decode_mark(data, named_resources):
    return None if data == empty_mark else generation_mark(*mark_layout.unpack(data), named_resources=named_resources)


def operator_exchange(vm, command, frame, wallet, stored):
    tag, version, operation, status, sequence = header.unpack_from(frame)
    require(tag == b"PKU1" and version == 1 and status == 0 and sequence == 1 and
            operation == credential_operations.get(command) and
            not any(memoryview(frame)[padding_offset:]), "Invalid private credential exchange")
    scope, number = struct.unpack_from("<16sQ", frame, identity_offset)
    require(scope == realm and number > 0, "Invalid credential account binding")
    with memoryview(frame) as data:
        identity = data[identity_offset:secret_offset]
        secret = data[secret_offset:padding_offset]
        if operation == issue:
            save_credential(*wallet, identity, secret)
            secret[:] = bytes(secret_size)
        else:
            require(not any(secret) and identity == memoryview(stored)[8:credential_file_header.size],
                    "Selected credential belongs to a different account")
            secret[:] = memoryview(stored)[-secret_size:]
    vm.send(frame)


def named_packet(operation, sequence, payload=named_empty):
    return header.pack(b"PKN1", 1, operation, 0, sequence) + payload


def named_exchange(vm, command, frame, selection, selection_sent):
    tag, version, operation, status, sequence = header.unpack_from(frame)
    require(tag == b"PKN1" and version == 1 and operation == named_operations[command],
            "Invalid named resource exchange")
    name, generation, data = selection
    payload = frame[header.size:]
    if not selection_sent:
        require(sequence == 1 and not status and payload == named_empty, "Invalid named resource selection request")
        selected = named_layout.pack(generation, data, len(name), name)
        vm.send(named_packet(operation, 1, selected + bytes(len(named_empty) - len(selected))))
        return None
    require(sequence == 2 and not any(payload[named_layout.size:]), "Invalid named resource result")
    if status == 1:
        actual, actual_data, length, returned_name = named_layout.unpack_from(payload)
        require(actual > 0 and length == len(name) and returned_name == name.ljust(16, b"\0") and
                not any(payload[13:16]), "Invalid returned resource identity")
        if command == "publish-named":
            require(actual > generation and actual_data == 0, "Invalid committed resource generation")
        else:
            require((generation == 0 or generation == actual) and (command == "read-named" or actual_data == 0),
                    "Unexpected returned resource generation")
    else:
        actual, actual_data = 0, 0
        allowed = (2, 3) if command == "read-named" else (4,)
        require(status in allowed and payload == named_empty, "Unexpected named resource status")
    vm.send(named_packet(operation, 2))
    return status, actual, actual_data


def boot(system, state, command, authority, wallet, stored, selection=None):
    with tempfile.TemporaryDirectory(prefix="pumpkin_user_") as private:
        monitor = Path(private) / "qmp"
        drive = str(state / "work.img").replace(",", ",,")
        vm = private_vm(qemu_command(system / "xos-install.iso", iso=True, work_disk=drive, qmp=monitor))
        try:
            vm.scan_boot(b"xos64> ")
            vm.send(b"run\r")
            marker = header.pack(b"PKA1", 1, ready, 0, 0)
            vm.scan_boot(marker)
            remainder = bytearray(2 * mark_layout.size)
            vm.receive(remainder, time.monotonic() + 12)
            require(not any(remainder), "Invalid private guest readiness frame")
            vm.send(generation_packet(ready, scenarios[command], 0))
            sequence = 1
            credential_seen = False
            selection_sent = False
            named_result = None
            for _ in range(20):
                frame = bytearray(frame_size)
                try:
                    vm.receive(frame, time.monotonic() + 12)
                    tag, version, operation, status, serial = header.unpack_from(frame)
                    if tag == b"PKU1":
                        require(not credential_seen, "Repeated private credential request")
                        if command == "enroll":
                            committed = authority.read()
                            require(committed is not None and committed.revision == 2,
                                    "Credential issue has no confirmed account publication")
                        operator_exchange(vm, command, frame, wallet, stored)
                        credential_seen = True
                        continue
                    if tag == b"PKN1":
                        require(selection is not None and named_result is None, "Unexpected named resource frame")
                        named_result = named_exchange(vm, command, frame, selection, selection_sent)
                        selection_sent = True
                        continue
                    require(tag == b"PKA1" and version == 1 and serial == sequence,
                            "Invalid generation frame from login guest")
                    expected, value = frame[header.size:header.size + mark_layout.size], frame[-mark_layout.size:]
                    if operation == read:
                        require(status == 0 and expected == empty_mark and value == empty_mark,
                                "Invalid generation read from login guest")
                        selected = authority.read()
                        encoded = empty_mark if selected is None else mark_layout.pack(
                            selected.realm, selected.revision, selected.length, selected.checksum)
                        reply = generation_packet(read, int(selected is None), sequence, encoded)
                    elif operation == publish:
                        require(status == 0 and command in ("enroll", "revoke", "publish-named", "erase-named"),
                                "Generation publication is unavailable in this operation")
                        candidate = decode_mark(value, authority.named_resources)
                        require(candidate is not None, "Missing generation publication")
                        result = authority.publish(decode_mark(expected, authority.named_resources), candidate)
                        codes = {publish_result.committed: 0, publish_result.conflict: 1,
                                 publish_result.unchanged: 2, publish_result.outcome_unknown: 3}
                        reply = generation_packet(publish, codes[result], sequence)
                    else:
                        require(operation == finish and expected == empty_mark and value == empty_mark,
                                "Invalid final login guest response")
                        vm.send(generation_packet(finish, 0, sequence))
                        time.sleep(0.15)
                        quit_qmp(monitor)
                        require(vm.process.wait(timeout=8) == 0, "Private guest shutdown failed")
                        if command in ("read-resource", "read-named") and status in resource_errors:
                            raise login_error(resource_errors[status])
                        require(credential_seen == (command in credential_operations), "Missing private credential exchange")
                        if selection is not None:
                            require(named_result is not None and status == named_result[0],
                                    "Named resource result was not confirmed")
                            return named_result
                        require(status == 1 or (status == 2 and command in submission_commands),
                                "Private login did not complete; check the account before retrying enrollment")
                        return status
                    vm.send(reply)
                    sequence += 1
                finally:
                    wipe(frame)
            raise login_error("Private login exceeded the frame budget")
        finally:
            vm.close()


def named_profile(system):
    return json.loads((system / "manifest.json").read_bytes()).get("pumpkin_named_resource_store") is True


def operate(system, state, command, path, selection=None):
    binding = bind_system(system)
    named = named_profile(system)
    require(command != "read-resource" or (broker_artifact in binding[2] and not named),
            "Select the private Pumpkin sealed resource image")
    require((selection is not None) == (command in named_operations) and
            (selection is None or named and broker_artifact in binding[2]), "Select the private named resource image")
    with private_directory(state) as descriptor:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        disk = os.stat("work.img", dir_fd=descriptor, follow_symlinks=False)
        require(stat.S_ISREG(disk.st_mode) and disk.st_uid == os.geteuid() and disk.st_nlink == 1,
                "Invalid private work disk")
        authority = generation_authority(state / "authority", realm, named_resources=named)
        previous = authority.read()
        require((previous is None) == (command == "enroll"),
                "Enrollment requires a new installation; restore or inspect an existing installation explicitly")
        stored = bytearray(file_size)
        try:
            if command not in credential_operations:
                result = boot(system, state, command, authority, None, stored, selection)
            else:
                with credential_file(path, command == "enroll") as wallet:
                    if command in submission_commands:
                        read_credential(wallet[0], stored)
                    result = boot(system, state, command, authority, wallet, stored, selection)
            require(bind_system(system) == binding, "Login image receipt changed during operation")
            final = authority.read()
            mutation = command in ("publish-named", "erase-named") and result[0] == 1
            expected = 2 if command == "enroll" else previous.revision + (command == "revoke" or mutation)
            require(final is not None and final.revision == expected,
                    "Independent account generation did not confirm the expected state")
            require(previous is None or expected != previous.revision or final == previous,
                    "The named resource or account mark unexpectedly changed")
            if command == "publish-named" and mutation:
                require(result[1] == expected, "Published resource differs from the independent generation")
            return result
        finally:
            wipe(stored)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", *scenarios))
    parser.add_argument("--system", type=Path)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--credential-file", type=Path)
    parser.add_argument("--resource-name")
    parser.add_argument("--generation", type=int)
    parser.add_argument("--resource-value", type=int, help="unsigned 32-bit value for publish-named")
    args = parser.parse_args()
    if args.operation != "prepare" and args.system is None:
        parser.error("a matching --system is required")
    if (args.operation in credential_operations) != (args.credential_file is not None):
        parser.error("--credential-file is required for credential submission and enrollment")
    selected = None
    if args.operation in named_operations:
        if args.resource_name is None or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,15}", args.resource_name) is None:
            parser.error("select a logical resource name of 1 to 16 characters")
        if (args.generation is None and args.operation != "read-named") or not 0 <= (args.generation or 0) < 2**64:
            parser.error("specify the expected unsigned generation for a mutation")
        if args.operation == "erase-named" and args.generation == 0:
            parser.error("erase requires the current resource generation")
        if (args.operation == "publish-named") != (args.resource_value is not None) or not 0 <= (args.resource_value or 0) < 2**32:
            parser.error("publish requires an unsigned 32-bit resource value")
        selected = args.resource_name.encode("ascii"), args.generation or 0, args.resource_value or 0
    elif args.resource_name is not None or args.generation is not None or args.resource_value is not None:
        parser.error("resource fields require a named resource operation")
    try:
        state = args.state.absolute()
        if args.operation == "prepare":
            if args.system is not None:
                bind_system(args.system)
            prepare(state, args.system is not None and named_profile(args.system))
            print("Private Pumpkin installation prepared")
            return 0
        path = args.credential_file.absolute() if args.credential_file is not None else None
        result = operate(args.system.absolute(), state, args.operation, path, selected)
        if selected is not None:
            result, generation, data = result
            if result == 1:
                if args.operation == "read-named":
                    print(f"Pumpkin named resource generation {generation} value {data}")
                else:
                    print(f"Pumpkin named resource generation {generation} confirmed")
                return 0
            if result in (3, 4):
                print("Pumpkin named resource read denied" if result == 3 else "Pumpkin named resource generation conflict")
                return result + 1
        if result == 2:
            print("Pumpkin login denied")
            return 3
        print({"enroll": "Pumpkin credential issued to your private file",
               "login": "Pumpkin login confirmed and session logged out",
               "read-resource": "Pumpkin sealed resource read confirmed and session logged out",
               "revoke": "Pumpkin credential revoked"}[args.operation])
        return 0
    except login_error as error:
        parser.exit(1, str(error) + "\n")
    except (OSError, ValueError, KeyError, TypeError, struct.error, subprocess.SubprocessError, generation_error):
        parser.exit(1, "Private Pumpkin operation could not be confirmed; do not repeat enrollment automatically\n")


if __name__ == "__main__":
    raise SystemExit(main())
