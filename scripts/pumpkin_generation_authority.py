# SPDX-License-Identifier: Apache-2.0
"""Independent generation record for explicit Pumpkin developer profiles."""

from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum, auto
import fcntl
import hashlib
import os
from pathlib import Path
import stat
import struct


_record = struct.Struct("<8s16sQI32s")
_tag = b"PUMGEN\0\1"
_named_tag = b"PUMGEN\0\2"
_digest_size = 32
_record_size = _record.size + _digest_size
_zero_digest = bytes(_digest_size)
_max_revision = (1 << 64) - 1
_active = "generation"
_staged = "pending"
_directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def _valid_realm(realm):
    return isinstance(realm, bytes) and len(realm) == 16 and any(realm)


@dataclass(frozen=True)
class generation_mark:
    realm: bytes
    revision: int
    length: int
    checksum: bytes
    named_resources: bool = False

    def __post_init__(self):
        # P0 has a 48-byte header, up to 64 accounts of 68 bytes, and
        # a 32-byte checksum. The authority stores only that checksum.
        envelope = 144 if self.named_resources else 0
        if (not _valid_realm(self.realm) or type(self.revision) is not int or
                not 1 <= self.revision <= _max_revision or type(self.length) is not int or
                type(self.named_resources) is not bool or
                not 80 + envelope <= self.length <= 4432 + envelope or
                (self.length - 80 - envelope) % 68 != 0 or
                not isinstance(self.checksum, bytes) or len(self.checksum) != _digest_size):
            raise ValueError("invalid Pumpkin generation mark")


class generation_error(RuntimeError):
    """The authority cannot establish a current, usable record."""


class publish_result(Enum):
    committed = auto()
    conflict = auto()
    unchanged = auto()
    outcome_unknown = auto()


class generation_authority:
    def __init__(self, root, realm, *, named_resources=False):
        if not _valid_realm(realm):
            raise ValueError("a nonzero realm is required")
        self._root = Path(root).absolute()
        self._realm = realm
        self._realm_directory = realm.hex()
        if type(named_resources) is not bool:
            raise ValueError("invalid generation format profile")
        self._named_resources = named_resources
        self._tag = _named_tag if named_resources else _tag

    @property
    def named_resources(self):
        return self._named_resources

    @contextmanager
    def _parent(self):
        descriptor = os.open(self._root, _directory_flags)
        try:
            info = os.fstat(descriptor)
            if info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise generation_error("authority root must be private to its owner")
            yield descriptor
        finally:
            os.close(descriptor)

    @contextmanager
    def _locked(self, parent, lock):
        descriptor = os.open(self._realm_directory, _directory_flags, dir_fd=parent)
        try:
            info = os.fstat(descriptor)
            if info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise generation_error("authority directory must be private to its owner")
            # All participants lock the same directory inode. Replacing the
            # data record does not replace the inode carrying the lock.
            fcntl.flock(descriptor, lock)
            yield descriptor
        finally:
            os.close(descriptor)

    def _read_record(self, directory):
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        descriptor = os.open(_active, flags, dir_fd=directory)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or
                    info.st_mode & 0o077 or info.st_nlink != 1 or info.st_size != _record_size):
                raise generation_error("invalid authority record file")
            data = stream.read(_record_size + 1)
        if len(data) != _record_size or hashlib.sha256(data[:_record.size]).digest() != data[_record.size:]:
            raise generation_error("corrupt authority record")
        tag, realm, revision, length, checksum = _record.unpack_from(data)
        if tag != self._tag or realm != self._realm:
            raise generation_error("wrong authority format or realm")
        if revision == 0 and length == 0 and checksum == _zero_digest:
            return None
        try:
            return generation_mark(realm, revision, length, checksum, self.named_resources)
        except ValueError as error:
            raise generation_error("invalid authority generation fields") from error

    def _stage(self, directory, mark):
        if mark is None:
            fields = _record.pack(self._tag, self._realm, 0, 0, _zero_digest)
        else:
            fields = _record.pack(self._tag, mark.realm, mark.revision, mark.length, mark.checksum)
        data = fields + hashlib.sha256(fields).digest()
        # A killed writer can leave one staged record. It is never authoritative.
        try:
            os.unlink(_staged, dir_fd=directory)
        except FileNotFoundError:
            pass
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        descriptor = os.open(_staged, flags, 0o600, dir_fd=directory)
        with os.fdopen(descriptor, "wb") as stream:
            if stream.write(data) != len(data):
                raise generation_error("short authority stage write")
            stream.flush()
            os.fsync(stream.fileno())

    def _install(self, directory, mark):
        os.replace(_staged, _active, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
        if self._read_record(directory) != mark:
            raise generation_error("authority readback did not match publication")

    def provision(self):
        """Create a new realm directory with an explicit uninitialized record."""
        with self._parent() as parent:
            os.mkdir(self._realm_directory, 0o700, dir_fd=parent)
            os.fsync(parent)
            with self._locked(parent, fcntl.LOCK_EX) as directory:
                self._stage(directory, None)
                self._install(directory, None)

    def read(self):
        """Return the stable current mark, or None for a provisioned blank realm."""
        try:
            with self._parent() as parent, self._locked(parent, fcntl.LOCK_SH) as directory:
                mark = self._read_record(directory)
                # Seal an already visible replacement if its writer died
                # after rename and before completing the directory sync.
                os.fsync(directory)
                return mark
        except OSError as error:
            raise generation_error("authority record unavailable") from error

    def publish(self, expected, next_mark):
        """Compare the full current mark and durably advance one revision."""
        if (not isinstance(next_mark, generation_mark) or next_mark.realm != self._realm or
                next_mark.named_resources != self.named_resources or
                (expected is not None and
                 (not isinstance(expected, generation_mark) or expected.realm != self._realm or
                  expected.named_resources != self.named_resources))):
            raise ValueError("authority publication does not match its configured realm and format")
        previous = 0 if expected is None else expected.revision
        if previous == _max_revision or next_mark.revision != previous + 1:
            raise ValueError("authority publication must advance one revision without overflow")

        try:
            with self._parent() as parent, self._locked(parent, fcntl.LOCK_EX) as directory:
                current = self._read_record(directory)
                os.fsync(directory)
                if current != expected:
                    return publish_result.conflict
                try:
                    self._stage(directory, next_mark)
                except (OSError, generation_error):
                    if self._read_record(directory) == current:
                        return publish_result.unchanged
                    return publish_result.outcome_unknown
                self._install(directory, next_mark)
                return publish_result.committed
        except (OSError, generation_error):
            return publish_result.outcome_unknown
