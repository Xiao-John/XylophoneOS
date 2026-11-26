#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Enroll, submit or revoke an operator-held Pumpkin credential in a private VM."""

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
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
scenarios = {"enroll": 4, "login": 5, "revoke": 6}
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


def prepare(state):
    state.mkdir(mode=0o700)
    with private_directory(state) as descriptor:
        authority_path = state / "authority"
        authority_path.mkdir(mode=0o700)
        generation_authority(authority_path, realm).provision()
        install_disk(state / "work.img")
        os.fsync(descriptor)


def bind_system(system):
    manifest = system / "manifest.json"
    checked = json.loads(manifest.read_bytes())
    require(checked.get("pumpkin_user_login") is True, "Select the private operator login image")
    names = ("xos-install.iso", "user_files.image.elf", "user_supervisor.image.elf",
             "user_pumpkin_durable.image.elf", "user_p2_anchor_proxy.image.elf", "user_pumpkin_holder.image.elf")
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


def decode_mark(data):
    return None if data == empty_mark else generation_mark(*mark_layout.unpack(data))


def operator_exchange(vm, command, frame, wallet, stored):
    tag, version, operation, status, sequence = header.unpack_from(frame)
    require(tag == b"PKU1" and version == 1 and status == 0 and sequence == 1 and
            operation == {"enroll": issue, "login": submit}.get(command) and
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


def boot(system, state, command, authority, wallet, stored):
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
                        require(status == 0 and command in ("enroll", "revoke"),
                                "Generation publication is unavailable in this operation")
                        candidate = decode_mark(value)
                        require(candidate is not None, "Missing generation publication")
                        result = authority.publish(decode_mark(expected), candidate)
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
                        require(status == 1 or (status == 2 and command == "login"),
                                "Private login did not complete; check the account before retrying enrollment")
                        require(credential_seen == (command != "revoke"), "Missing private credential exchange")
                        return status
                    vm.send(reply)
                    sequence += 1
                finally:
                    wipe(frame)
            raise login_error("Private login exceeded the frame budget")
        finally:
            vm.close()


def operate(system, state, command, path):
    binding = bind_system(system)
    with private_directory(state) as descriptor:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        disk = os.stat("work.img", dir_fd=descriptor, follow_symlinks=False)
        require(stat.S_ISREG(disk.st_mode) and disk.st_uid == os.geteuid() and disk.st_nlink == 1,
                "Invalid private work disk")
        authority = generation_authority(state / "authority", realm)
        previous = authority.read()
        require((previous is None) == (command == "enroll"),
                "Enrollment requires a new installation; restore or inspect an existing installation explicitly")
        stored = bytearray(file_size)
        try:
            if command == "revoke":
                result = boot(system, state, command, authority, None, stored)
            else:
                with credential_file(path, command == "enroll") as wallet:
                    if command == "login":
                        read_credential(wallet[0], stored)
                    result = boot(system, state, command, authority, wallet, stored)
            require(bind_system(system) == binding, "Login image receipt changed during operation")
            final = authority.read()
            expected = 2 if command == "enroll" else previous.revision + (command == "revoke")
            require(final is not None and final.revision == expected,
                    "Independent account generation did not confirm the expected state")
            require(command != "login" or final == previous, "A login unexpectedly changed the account store")
            return result
        finally:
            wipe(stored)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", *scenarios))
    parser.add_argument("--system", type=Path)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--credential-file", type=Path)
    args = parser.parse_args()
    if args.operation != "prepare" and args.system is None:
        parser.error("a matching --system is required")
    if (args.operation in ("enroll", "login")) != (args.credential_file is not None):
        parser.error("--credential-file is required for enroll and login only")
    try:
        state = args.state.absolute()
        if args.operation == "prepare":
            prepare(state)
            print("Private Pumpkin installation prepared")
            return 0
        path = args.credential_file.absolute() if args.credential_file is not None else None
        result = operate(args.system.absolute(), state, args.operation, path)
        if result == 2:
            print("Pumpkin login denied")
            return 3
        print({"enroll": "Pumpkin credential issued to your private file",
               "login": "Pumpkin login confirmed and session logged out",
               "revoke": "Pumpkin credential revoked"}[args.operation])
        return 0
    except login_error as error:
        parser.exit(1, str(error) + "\n")
    except (OSError, ValueError, KeyError, TypeError, struct.error, subprocess.SubprocessError, generation_error):
        parser.exit(1, "Private Pumpkin operation could not be confirmed; do not repeat enrollment automatically\n")


if __name__ == "__main__":
    raise SystemExit(main())
