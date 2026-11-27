#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Manage Pumpkin login in a private VM configured by a trusted operator."""

import argparse
from contextlib import ExitStack, contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import socket
import stat
import struct
import subprocess
import tempfile
import time

from make_work_disk import create_fat32
from pumpkin_generation_authority import generation_authority, generation_error, generation_mark, publish_result
from pumpkin_generation_provider import developer_realm, encode_mark, load_profile, provider_client, require_uid
from run_qemu import qemu_command


realm = developer_realm
header = struct.Struct("<4sHBBQ")
account_selection = struct.Struct("<I32s92x")
empty_account = bytes(account_selection.size)
account_name_pattern = r"[A-Za-z0-9][A-Za-z0-9._-]{0,31}"
first_account_command = "provision-first"
check_image_command = "check-image-update"
begin_image_command = "begin-image-update"
finish_image_command = "finish-image-update"
cancel_image_command = "cancel-image-update"
image_update_commands = (begin_image_command, finish_image_command, cancel_image_command)
duplicate_enrollment = 6
desktop_revoked = 7
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
named_operations = {"read-named": 1, "publish-named": 2, "erase-named": 3, "import-fat": 4}
scenarios.update({"read-named": 9, "publish-named": 10, "erase-named": 11, "import-fat": 12})
scenarios.update({"desktop": 13, "desktop-admin": 14})
named_writes = ("publish-named", "erase-named", "import-fat")
desktop_commands = ("desktop", "desktop-admin")
submission_commands = ("login", "read-resource", "read-named", *desktop_commands)
credential_operations = {"enroll": issue, **dict.fromkeys(submission_commands, submit)}
named_layout = struct.Struct("<QIB3x16s")
named_empty = bytes(frame_size - header.size)
named_payload_size = len(named_empty) - named_layout.size
broker_artifact = "user_p2_sealed.image.elf"
resource_errors = {
    29: "Pumpkin resource session did not complete",
    32: "Pumpkin sealed broker could not start",
    33: "Pumpkin sealed broker startup was not confirmed",
    34: "Pumpkin sealed broker was not admitted",
    35: "Pumpkin sealed broker did not close cleanly",
}
directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
deployment_marker = "deployment.sha256"
image_update_tag = b"PUMIMG\0\1"
active_binding_tag = b"PUMACT\0\1"
image_update_record = struct.Struct("<8s32s32s64s")
image_update_size = image_update_record.size + hashlib.sha256().digest_size


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


def check_new_destination(path):
    with private_directory(path.parent) as parent:
        try:
            os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            return
    raise login_error("The selected credential destination already exists")


def read_credential(descriptor, record, installation_realm=realm):
    with memoryview(record) as data:
        offset = 0
        while offset < len(data):
            count = os.readv(descriptor, [data[offset:]])
            require(count != 0, "Incomplete private credential file")
            offset += count
    tag, scope, number = credential_file_header.unpack_from(record)
    require(tag == file_magic and scope == installation_realm and number > 0 and any(memoryview(record)[-secret_size:]),
            "Invalid private credential record")


def save_credential(descriptor, parent, identity, key):
    scope, number = struct.unpack("<16sQ", identity)
    require(any(scope) and number > 0 and any(key), "Invalid issued credential")
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


def prepare(state, named_resources=False, *, deployment=None, system=None):
    if deployment is not None:
        require(system is not None, "Select the deployment system image")
        select_deployment(system, bind_system(system), deployment)
        require(provider_client(deployment).read() is None, "The provider realm has already been used")
    state.mkdir(mode=0o700)
    with private_directory(state) as descriptor:
        if deployment is None:
            authority_path = state / "authority"
            authority_path.mkdir(mode=0o700)
            generation_authority(authority_path, realm, named_resources=named_resources).provision()
        install_disk(state / "work.img")
        if deployment is not None:
            marker = os.open(deployment_marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=descriptor)
            with os.fdopen(marker, "wb") as stream:
                stream.write(deployment.sha256.encode("ascii"))
                stream.flush()
                os.fsync(stream.fileno())
        os.fsync(descriptor)


def bind_system(system):
    manifest = system / "manifest.json"
    metadata = manifest.read_bytes()
    checked = json.loads(metadata)
    require(checked.get("pumpkin_user_login") is True and checked.get("pumpkin_operator_protocol") == 2,
            "Select a private operator login image built with this tool")
    names = ("xos-install.iso", "user_files.image.elf", "user_supervisor.image.elf",
             "user_pumpkin_durable.image.elf", "user_p2_anchor_proxy.image.elf", "user_pumpkin_holder.image.elf")
    if checked.get("pumpkin_user_resource") is True:
        names += (broker_artifact,)
    if "pumpkin_mobius_executable" in checked:
        names += ("user_display.image.elf", "user_interactiumd.image.elf")
    artifacts = {name: digest(system / name) for name in names}
    require(all(checked["artifacts"][name]["sha256"] == value for name, value in artifacts.items()),
            "Login image differs from its build receipt")
    return checked["build_id"], hashlib.sha256(metadata).hexdigest(), artifacts


def select_deployment(system, binding, deployment):
    metadata = (system / "manifest.json").read_bytes()
    require(hashlib.sha256(metadata).hexdigest() == binding[1], "Login image manifest changed")
    manifest = json.loads(metadata)
    installed_realm = manifest.get("pumpkin_deployment_realm")
    named = manifest.get("pumpkin_named_resource_store") is True
    if deployment is None:
        require(installed_realm is None, "This login image requires its independent deployment provider")
    else:
        require(deployment.realm.hex() == installed_realm and deployment.system_manifest_sha256 == binding[1]
                and deployment.named_resources == named, "System image does not match the deployment profile")
    return named


def read_deployment_marker(descriptor):
    try:
        marker = os.open(deployment_marker, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
    except FileNotFoundError:
        return None
    with os.fdopen(marker, "rb") as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600
                and info.st_uid == os.geteuid() and info.st_nlink == 1,
                "Invalid private installation binding")
        return stream.read(image_update_size + 1)


def active_binding(deployment):
    fields = active_binding_tag + bytes.fromhex(deployment.sha256)
    return fields + hashlib.sha256(fields).digest()


def matches_active_binding(marker, deployment):
    return deployment is not None and marker in (deployment.sha256.encode("ascii"), active_binding(deployment))


def check_installation(descriptor, deployment):
    marker = read_deployment_marker(descriptor)
    if marker is None:
        require(deployment is None, "The installation is missing its deployment binding")
        return
    require(not marker.startswith(image_update_tag), "Pumpkin image maintenance is in progress")
    require(matches_active_binding(marker, deployment),
            "The installation does not match the deployment profile")


@contextmanager
def locked_state(state):
    with private_directory(state) as descriptor:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        disk = os.stat("work.img", dir_fd=descriptor, follow_symlinks=False)
        require(stat.S_ISREG(disk.st_mode) and disk.st_uid == os.geteuid() and disk.st_nlink == 1,
                "Invalid private work disk")
        yield descriptor


@contextmanager
def locked_installation(state, deployment):
    with locked_state(state) as descriptor:
        check_installation(descriptor, deployment)
        yield descriptor


def verify_update_roles(current, replacement):
    require_uid(current.operator_uid)
    require(current.realm == replacement.realm, "The replacement changes the installation realm")
    require((current.operator_uid, current.provider_uid, current.socket_path) ==
            (replacement.operator_uid, replacement.provider_uid, replacement.socket_path),
            "The replacement changes the deployment roles or provider socket")
    require(current.named_resources == replacement.named_resources,
            "The replacement changes the account or resource storage configuration")


def verify_update_image(system, profile):
    binding = bind_system(system)
    select_deployment(system, binding, profile)
    return binding


def verify_update_pair(system, current, replacement_system, replacement):
    current_binding = verify_update_image(system, current)
    replacement_binding = verify_update_image(replacement_system, replacement)
    require((broker_artifact in current_binding[2]) == (broker_artifact in replacement_binding[2]),
            "The replacement changes the account or resource storage configuration")
    return current_binding, replacement_binding


def check_image_update(system, state, current, replacement_system, replacement):
    verify_update_roles(current, replacement)
    current_binding, replacement_binding = verify_update_pair(system, current, replacement_system, replacement)
    try:
        with locked_installation(state, current):
            return {
                "status": "bindings_compatible",
                "current_manifest_sha256": current_binding[1],
                "replacement_manifest_sha256": replacement_binding[1],
            }
    except BlockingIOError as error:
        raise login_error("The private Pumpkin installation is busy") from error


def replace_deployment_marker(directory, content):
    temporary = ".deployment-" + os.urandom(12).hex()
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, deployment_marker, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass


def pending_update_mark(value, current, replacement):
    require(value is not None and len(value) == image_update_size
            and hashlib.sha256(value[:image_update_record.size]).digest() == value[image_update_record.size:],
            "The installation has no valid pending image update")
    tag, old, new, mark = image_update_record.unpack_from(value)
    require((tag, old, new) == (image_update_tag, bytes.fromhex(current.sha256), bytes.fromhex(replacement.sha256)),
            "The pending image update belongs to a different deployment pair")
    return mark


def maintain_image(command, state, system, current, replacement_system, replacement):
    verify_update_roles(current, replacement)
    require(current.system_manifest_sha256 != replacement.system_manifest_sha256,
            "Select two distinct deployment images")
    if command == begin_image_command:
        verify_update_pair(system, current, replacement_system, replacement)
    elif command == finish_image_command:
        verify_update_image(replacement_system, replacement)
    else:
        verify_update_image(system, current)

    with locked_state(state) as directory:
        marker = read_deployment_marker(directory)
        if command == begin_image_command:
            if matches_active_binding(marker, current):
                mark = encode_mark(provider_client(current).read())
                fields = image_update_record.pack(image_update_tag, bytes.fromhex(current.sha256),
                                                  bytes.fromhex(replacement.sha256), mark)
                replace_deployment_marker(directory, fields + hashlib.sha256(fields).digest())
            else:
                pending_update_mark(marker, current, replacement)
                os.fsync(directory)
            return {"status": "image_update_pending"}
        target = replacement if command == finish_image_command else current
        if matches_active_binding(marker, target):
            provider_client(target).read()
            os.fsync(directory)
            return {"status": "image_binding_already_active", "profile_sha256": target.sha256}
        mark = pending_update_mark(marker, current, replacement)
        require(encode_mark(provider_client(target).read()) == mark,
                "The independent generation changed during image maintenance")
        replace_deployment_marker(directory, active_binding(target))
        status = "image_update_activated" if command == finish_image_command else "image_update_cancelled"
        return {"status": status, "profile_sha256": target.sha256}


@contextmanager
def sealed_login_image(path, expected_sha256):
    descriptor = os.memfd_create("pumpkin-login-iso", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    try:
        source = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(source, "rb") as stream, os.fdopen(os.dup(descriptor), "wb") as captured:
            require(stat.S_ISREG(os.fstat(source).st_mode), "Login image must be a regular file")
            shutil.copyfileobj(stream, captured)
        seals = fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_GROW | fcntl.F_SEAL_WRITE | fcntl.F_SEAL_SEAL
        fcntl.fcntl(descriptor, fcntl.F_ADD_SEALS, seals)
        reference = Path("/proc/self/fd") / str(descriptor)
        require(digest(reference) == expected_sha256, "The sealed login image differs from its deployment profile")
        yield reference, descriptor
    finally:
        os.close(descriptor)


class private_vm:
    """Unlike the general test console, this pipe never accumulates a recording."""

    def __init__(self, command, *, pass_fds=()):
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, bufsize=0, close_fds=True, pass_fds=pass_fds)
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


def operator_exchange(vm, command, frame, wallet, stored, installation_realm):
    tag, version, operation, status, sequence = header.unpack_from(frame)
    require(tag == b"PKU1" and version == 1 and status == 0 and sequence == 1 and
            operation == credential_operations.get(command) and
            not any(memoryview(frame)[padding_offset:]), "Invalid private credential exchange")
    scope, number = struct.unpack_from("<16sQ", frame, identity_offset)
    require(scope == installation_realm and number > 0, "Invalid credential account binding")
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
    return header.pack(b"PKN1", 2, operation, 0, sequence) + payload


def named_exchange(vm, command, frame, selection, selection_sent):
    tag, version, operation, status, sequence = header.unpack_from(frame)
    require(tag == b"PKN1" and version == 2 and operation == named_operations[command],
            "Invalid named resource exchange")
    name, generation, data, source = selection
    payload = frame[header.size:]
    if not selection_sent:
        require(sequence == 1 and not status and payload == named_empty, "Invalid named resource selection request")
        selected = named_layout.pack(generation, len(source) if source else data, len(name), name)
        vm.send(named_packet(operation, 1, selected + source.ljust(named_payload_size, b"\0")))
        return None
    require(sequence == 2, "Invalid named resource result")
    returned = b""
    if status == 1:
        actual, actual_data, length, returned_name = named_layout.unpack_from(payload)
        require(actual > 0 and length == len(name) and returned_name == name.ljust(16, b"\0") and
                not any(payload[13:16]), "Invalid returned resource identity")
        if command in ("publish-named", "import-fat"):
            require(actual > generation and actual_data == 0, "Invalid committed resource generation")
        else:
            require(generation == 0 or generation == actual, "Unexpected returned resource generation")
        if command == "read-named":
            require(0 < actual_data <= 32, "Invalid returned named resource length")
            returned = payload[named_layout.size:named_layout.size + actual_data]
        else:
            require(actual_data == 0, "Unexpected named resource data")
        require(not any(payload[named_layout.size + len(returned):]), "Invalid named resource padding")
    else:
        actual = 0
        allowed = (2, 3) if command == "read-named" else (4, 5) if command == "import-fat" else (4,)
        require(status in allowed and payload == named_empty, "Unexpected named resource status")
    vm.send(named_packet(operation, 2))
    return status, actual, returned


def boot(system, state, command, authority, previous, path, stored, account, selection, display, revoke_requested,
         *, first_account=False, installation_realm=realm, expected_iso_sha256=None):
    with tempfile.TemporaryDirectory(prefix="pumpkin_user_") as private, ExitStack() as close_wallet:
        monitor = Path(private) / "qmp"
        drive = str(state / "work.img").replace(",", ",,")
        image = system / "xos-install.iso"
        descriptors = ()
        if expected_iso_sha256 is not None:
            image, pinned = close_wallet.enter_context(sealed_login_image(image, expected_iso_sha256))
            descriptors = (pinned,)
        vm = private_vm(qemu_command(image, iso=True, work_disk=drive, qmp=monitor, display=display),
                        pass_fds=descriptors)
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
            account_seen = False
            destination_seen = False
            wallet = None
            selection_sent = False
            named_result = None
            desktop_end = None
            admin_polls = 0
            revocation_sent = revocation_attempted = revocation_published = False
            remaining_frames = 20
            while remaining_frames:
                frame = bytearray(frame_size)
                try:
                    vm.receive(frame, desktop_end if desktop_end is not None else time.monotonic() + 12)
                    tag, version, operation, status, serial = header.unpack_from(frame)
                    if tag == b"PKD1":
                        admin_polls += 1
                        require(command == "desktop-admin" and account_seen and credential_seen and
                                not revocation_sent and 1 <= admin_polls <= 1800 and serial == admin_polls and
                                version == 1 and operation == scenarios[command] and status == 0 and
                                not any(frame[header.size:]), "Invalid live desktop administration frame")
                        revocation_sent = bool(revoke_requested())
                        header.pack_into(frame, 0, tag, version, operation, int(revocation_sent), serial)
                        vm.send(frame)
                        continue
                    remaining_frames -= 1
                    if tag == b"PKO1":
                        require(version == 1 and operation == scenarios[command] and status == 0 and
                                frame[header.size:] == empty_account, "Invalid private account selection prompt")
                        if not account_seen:
                            require(serial == 1, "Account selection out of sequence")
                            if first_account:
                                wallet = close_wallet.enter_context(credential_file(path, True))
                            flags = int(previous is None)
                            vm.send(header.pack(tag, version, operation, flags, serial) +
                                    account_selection.pack(len(account), account))
                            account_seen = True
                        else:
                            require(serial == 2 and command == "enroll" and not destination_seen and not credential_seen,
                                    "Unexpected credential destination prompt")
                            if wallet is None:
                                wallet = close_wallet.enter_context(credential_file(path, True))
                            destination_seen = True
                            vm.send(frame)
                        continue
                    require(account_seen, "Private operation arrived before account selection")
                    if tag == b"PKU1":
                        require(not credential_seen, "Repeated private credential request")
                        if command == "enroll":
                            committed = authority.read()
                            expected = 2 if previous is None else previous.revision + 1
                            require(destination_seen and committed is not None and committed.revision == expected,
                                    "Credential issue has no confirmed account publication")
                        try:
                            operator_exchange(vm, command, frame, wallet, stored, installation_realm)
                        finally:
                            wipe(stored)
                        credential_seen = True
                        if command in desktop_commands:
                            desktop_end = time.monotonic() + 31 * 60
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
                        live_revoke = command == "desktop-admin" and revocation_sent and not revocation_attempted
                        require(status == 0 and (command in ("enroll", "revoke", *named_writes) or live_revoke),
                                "Generation publication is unavailable in this operation")
                        candidate = decode_mark(value, authority.named_resources)
                        require(candidate is not None, "Missing generation publication")
                        if first_account:
                            require(wallet is not None and not credential_seen and
                                    candidate.revision == (2 if destination_seen else 1),
                                    "Publication is outside the first account operation")
                        revocation_attempted = revocation_attempted or live_revoke
                        result = authority.publish(decode_mark(expected, authority.named_resources), candidate)
                        if live_revoke:
                            revocation_published = result == publish_result.committed
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
                        if command in desktop_commands and status == 36 and not revocation_sent:
                            raise login_error("Pumpkin desktop could not start or its logout was not confirmed")
                        if command == "enroll" and status == duplicate_enrollment:
                            require(not credential_seen and wallet is None, "Duplicate enrollment attempted credential issue")
                            return status
                        require(credential_seen == (command in credential_operations), "Missing private credential exchange")
                        if selection is not None:
                            require(named_result is not None and status == named_result[0],
                                    "Named resource result was not confirmed")
                            return named_result
                        if command == "desktop-admin" and revocation_sent:
                            require(status == desktop_revoked and revocation_published,
                                    "Pumpkin live revocation could not be confirmed; check durable state before retrying")
                            return status
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


def operate(system, state, command, path, selection=None, account=b"alice", *, display=None,
            revoke_requested=None, deployment=None):
    first_account = command == first_account_command
    if first_account:
        require(path is not None and isinstance(account, bytes) and
                re.fullmatch(account_name_pattern.encode("ascii"), account),
                "First account provisioning needs a valid name and private credential destination")
        command = "enroll"
    binding = bind_system(system)
    require(command not in desktop_commands or "user_interactiumd.image.elf" in binding[2],
            "Select a private login image with a bound Mobius executable")
    require((revoke_requested is not None) == (command == "desktop-admin"),
            "Live revocation requires an explicit administration source")
    named = select_deployment(system, binding, deployment)
    require(command != "read-resource" or (broker_artifact in binding[2] and not named),
            "Select the private Pumpkin sealed resource image")
    require((selection is not None) == (command in named_operations) and
            (selection is None or named and broker_artifact in binding[2]), "Select the private named resource image")
    with locked_installation(state, deployment) as directory:
        if deployment is not None:
            # A prior marker rename can be visible before its directory sync.
            # Do not let a guest advance the independent generation until it is durable.
            os.fsync(directory)
        installation_realm = realm if deployment is None else deployment.realm
        authority = (generation_authority(state / "authority", realm, named_resources=named)
                     if deployment is None else provider_client(deployment))
        previous = authority.read()
        if first_account:
            require(previous is None, "First account provisioning requires an unused installation")
        require(previous is not None or command == "enroll", "Enroll an account before using this installation")
        stored = bytearray(file_size)
        try:
            if command == "enroll":
                check_new_destination(path)
            elif command in submission_commands:
                with credential_file(path, False) as wallet:
                    read_credential(wallet[0], stored, installation_realm)
            result = boot(system, state, command, authority, previous, path, stored, account, selection, display,
                          revoke_requested, first_account=first_account, installation_realm=installation_realm,
                          expected_iso_sha256=binding[2]["xos-install.iso"] if deployment is not None else None)
            require(bind_system(system) == binding, "Login image receipt changed during operation")
            final = authority.read()
            if command == "enroll" and result == duplicate_enrollment:
                require(previous is not None and final == previous, "Duplicate enrollment changed the account store")
                raise login_error("The selected account is already enrolled")
            mutation = command in named_writes and result[0] == 1
            revoked = command == "desktop-admin" and result == desktop_revoked
            expected = 2 if previous is None else previous.revision + (command in ("enroll", "revoke") or mutation or revoked)
            require(final is not None and final.revision == expected,
                    "Independent account generation did not confirm the expected state")
            require(previous is None or expected != previous.revision or final == previous,
                    "The named resource or account mark unexpectedly changed")
            if command in ("publish-named", "import-fat") and mutation:
                require(result[1] == expected, "Published resource differs from the independent generation")
            return result
        finally:
            wipe(stored)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", first_account_command, check_image_command, *image_update_commands,
                                              *(item for item in scenarios if item != "desktop-admin")))
    parser.add_argument("--system", type=Path)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--credential-file", type=Path)
    parser.add_argument("--deployment-profile", type=Path)
    parser.add_argument("--deployment-profile-sha256")
    parser.add_argument("--replacement-system", type=Path)
    parser.add_argument("--replacement-deployment-profile", type=Path)
    parser.add_argument("--replacement-deployment-profile-sha256")
    parser.add_argument("--account", default=None, help="select an account name, default alice")
    parser.add_argument("--resource-name")
    parser.add_argument("--generation", type=int)
    parser.add_argument("--resource-value", type=int, help="unsigned 32-bit value for publish-named")
    parser.add_argument("--fat-source", help="absolute guest source file for import-fat")
    parser.add_argument("--display", help="QEMU display backend for the desktop operation")
    parser.add_argument("--revoke-on-signal", action="store_true", help="enable same-owner host SIGUSR1 to revoke the live desktop login")
    args = parser.parse_args()
    if (args.deployment_profile is None) != (args.deployment_profile_sha256 is None):
        parser.error("supply the deployment profile and its trusted SHA-256 together")
    image_operation = args.operation in (check_image_command, *image_update_commands)
    needs_current_image = args.operation not in ("prepare", finish_image_command) or (
        args.operation == "prepare" and args.deployment_profile is not None)
    if needs_current_image and args.system is None:
        parser.error("a matching --system is required")
    replacement_fields = (args.replacement_system, args.replacement_deployment_profile,
                          args.replacement_deployment_profile_sha256)
    if image_operation:
        if (args.deployment_profile is None or args.replacement_deployment_profile is None
                or args.replacement_deployment_profile_sha256 is None
                or (args.operation != cancel_image_command and args.replacement_system is None)):
            parser.error("the image operation requires both trusted deployment profiles and the affected systems")
    elif any(value is not None for value in replacement_fields):
        parser.error("replacement options require an image operation")
    if (args.operation in credential_operations or args.operation == first_account_command) != (args.credential_file is not None):
        parser.error("--credential-file is required for credential submission and enrollment")
    if args.display is not None and args.operation != "desktop":
        parser.error("--display requires the desktop operation")
    if args.revoke_on_signal and args.operation != "desktop":
        parser.error("--revoke-on-signal requires the desktop operation")
    account = "alice" if args.account is None else args.account
    if (((args.operation == "prepare" or image_operation) and args.account is not None) or
            re.fullmatch(account_name_pattern, account) is None):
        parser.error("select an account name of 1 to 32 characters for an account operation")
    selected = None
    if args.operation in named_operations:
        if args.resource_name is None or re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,15}", args.resource_name) is None:
            parser.error("select a logical resource name of 1 to 16 lowercase ASCII characters, starting with a letter or digit")
        if (args.generation is None and args.operation != "read-named") or not 0 <= (args.generation or 0) < 2**64:
            parser.error("specify the expected unsigned generation for a mutation")
        if args.operation == "erase-named" and args.generation == 0:
            parser.error("erase requires the current resource generation")
        if (args.operation == "publish-named") != (args.resource_value is not None) or not 0 <= (args.resource_value or 0) < 2**32:
            parser.error("publish requires an unsigned 32-bit resource value")
        if (args.operation == "import-fat") != (args.fat_source is not None):
            parser.error("import-fat requires its guest FAT source")
        try:
            source = args.fat_source.encode("utf-8") if args.fat_source is not None else b""
        except UnicodeError:
            parser.error("a FAT source path must be UTF-8")
        if args.fat_source is not None and (not source.startswith(b"/") or not 2 <= len(source) < named_payload_size or
                                           any(byte < 32 or byte in (92, 127) for byte in source)):
            parser.error("a FAT source must be an absolute guest path of 2 to 95 UTF-8 bytes")
        selected = args.resource_name.encode("ascii"), args.generation or 0, args.resource_value or 0, source
    elif args.resource_name is not None or args.generation is not None or args.resource_value is not None or args.fat_source is not None:
        parser.error("resource fields require a named resource operation")
    try:
        state = args.state.absolute()
        deployment = (load_profile(args.deployment_profile, args.deployment_profile_sha256)
                      if args.deployment_profile is not None else None)
        if image_operation:
            replacement = load_profile(args.replacement_deployment_profile, args.replacement_deployment_profile_sha256)
            if args.operation == check_image_command:
                result = check_image_update(args.system, state, deployment, args.replacement_system, replacement)
            else:
                result = maintain_image(args.operation, state, args.system, deployment,
                                        args.replacement_system, replacement)
            print(json.dumps(result, sort_keys=True))
            return 0
        if args.operation == "prepare":
            named = False
            if args.system is not None and deployment is None:
                named = select_deployment(args.system, bind_system(args.system), None)
            prepare(state, named, deployment=deployment, system=args.system)
            print("Private Pumpkin installation prepared")
            return 0
        path = args.credential_file.absolute() if args.credential_file is not None else None
        requested = False
        if args.revoke_on_signal:
            def request_revocation(signum, frame):
                nonlocal requested
                requested = True

            old_handler = signal.signal(signal.SIGUSR1, request_revocation)
            try:
                print(f"Live Pumpkin administration enabled for process {os.getpid()}", flush=True)
                result = operate(args.system.absolute(), state, "desktop-admin", path, account=account.encode("ascii"),
                                 display=args.display, revoke_requested=lambda: requested, deployment=deployment)
            finally:
                signal.signal(signal.SIGUSR1, old_handler)
        else:
            result = operate(args.system.absolute(), state, args.operation, path, selected, account.encode("ascii"),
                             display=args.display, deployment=deployment)
        if selected is not None:
            result, generation, data = result
            if result == 1:
                if args.operation == "read-named":
                    if len(data) == 4:
                        print(f"Pumpkin named resource generation {generation} value {int.from_bytes(data, 'little')}")
                    else:
                        print(f"Pumpkin named resource generation {generation} bytes {data.hex()}")
                else:
                    print(f"Pumpkin named resource generation {generation} confirmed")
                return 0
            if result in (3, 4, 5):
                print({3: "Pumpkin named resource read denied", 4: "Pumpkin named resource generation conflict",
                       5: "Pumpkin FAT source could not supply a pinned file of 1 to 32 bytes"}[result])
                return result + 1
        if result == 2:
            print("Pumpkin login denied")
            return 3
        if args.revoke_on_signal and result == desktop_revoked:
            print("Pumpkin revoked the account and retired the active Mobius session")
            return 0
        print({"enroll": "Pumpkin credential issued to your private file",
               first_account_command: "First Pumpkin account issued to your private file",
               "login": "Pumpkin login confirmed and session logged out",
               "desktop": "Mobius closed and Pumpkin confirmed logout",
               "read-resource": "Pumpkin sealed resource read confirmed and session logged out",
               "revoke": "Pumpkin credential revoked"}[args.operation])
        return 0
    except login_error as error:
        parser.exit(1, str(error) + "\n")
    except (OSError, ValueError, KeyError, TypeError, struct.error, subprocess.SubprocessError, generation_error):
        if args.operation == check_image_command:
            parser.exit(1, "Pumpkin image update bindings could not be confirmed\n")
        if image_operation:
            parser.exit(1, "Pumpkin image maintenance could not be confirmed; inspect or retry the same profiles\n")
        parser.exit(1, "Private Pumpkin operation could not be confirmed; do not repeat enrollment automatically\n")


if __name__ == "__main__":
    raise SystemExit(main())
