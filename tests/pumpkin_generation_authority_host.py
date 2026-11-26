# SPDX-License-Identifier: Apache-2.0
"""Exercise the independent Pumpkin record on the actual host filesystem."""

from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import select
import signal
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from pumpkin_generation_authority import generation_authority, generation_error, generation_mark, publish_result


_realm = b"test-realm-00001"
_max_revision = (1 << 64) - 1


def mark(revision, variant="a", length=80, realm=_realm):
    checksum = hashlib.sha256(f"{revision}:{variant}".encode()).digest()
    return generation_mark(realm, revision, length, checksum)


def empty_snapshot(revision):
    header = struct.pack("<8sII16sQII", b"PUMPKIN\0", 1, 80, _realm, revision, 0, 0)
    return header + hashlib.sha256(header).digest()


def child_main(command, directory, phase="replace", variant="a"):
    authority = generation_authority(Path(directory).parent, _realm)
    if command == "read":
        current = authority.read()
        print("blank" if current is None else f"{current.revision}:{current.checksum.hex()}", flush=True)
        return

    replace, sync = os.replace, os.fsync
    installed = False

    def stop_at_boundary():
        print("paused", flush=True)
        if sys.stdin.readline() != "release\n":
            raise RuntimeError("parent closed the process gate")

    def tracked_replace(*args, **kwargs):
        nonlocal installed
        if phase == "before_replace":
            stop_at_boundary()
        replace(*args, **kwargs)
        installed = True
        if phase == "after_replace":
            stop_at_boundary()

    def tracked_sync(descriptor):
        sync(descriptor)
        if installed and phase == "after_sync" and stat.S_ISDIR(os.fstat(descriptor).st_mode):
            stop_at_boundary()

    print("attempting", flush=True)
    with patch.object(os, "replace", tracked_replace), patch.object(os, "fsync", tracked_sync):
        print(authority.publish(mark(1), mark(2, variant)).name, flush=True)


@contextmanager
def child(*args):
    command = [sys.executable, "-B", __file__, "--child", *map(str, args)]
    with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, bufsize=0) as process:
        try:
            yield process
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)


def line(process):
    if not select.select([process.stdout], [], [], 10)[0]:
        raise AssertionError("authority process did not report its boundary")
    output = process.stdout.readline().decode().rstrip("\n")
    if not output:
        process.wait(timeout=10)
        raise AssertionError(process.stderr.read().decode())
    return output


class authority_test(unittest.TestCase):
    def setup_authority(self, name="authority"):
        root = self.root / name
        root.mkdir(mode=0o700)
        return root / _realm.hex(), generation_authority(root, _realm)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pumpkin_generation_")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.directory, self.authority = self.setup_authority()

    def start_authority(self, authority):
        authority.provision()
        self.assertEqual(authority.publish(None, mark(1)), publish_result.committed)

    def test_named_generation_has_its_own_record_and_length_policy(self):
        directory, account_format = self.setup_authority("named")
        named_format = generation_authority(directory.parent, _realm, named_resources=True)
        named_format.provision()
        self.assertIsNone(named_format.read())
        with self.assertRaises(generation_error):
            account_format.read()
        with self.assertRaises(ValueError):
            named_format.publish(None, mark(1))
        allowed = generation_mark(_realm, 1, 4576, mark(1).checksum, named_resources=True)
        self.assertEqual(named_format.publish(None, allowed), publish_result.committed)
        reopened = generation_authority(directory.parent, _realm, named_resources=True)
        self.assertEqual(reopened.read(), allowed)
        with self.assertRaises(generation_error):
            account_format.read()
        with self.assertRaises(ValueError):
            generation_mark(_realm, 2, 80, mark(2).checksum, named_resources=True)
        with self.assertRaises(ValueError):
            generation_mark(_realm, 2, 4576, mark(2).checksum)

    def assert_fresh_read(self, directory, expected):
        with child("read", directory) as process:
            self.assertEqual(line(process), f"{expected.revision}:{expected.checksum.hex()}")
            self.assertEqual(process.wait(timeout=10), 0)

    def test_explicit_provisioning_and_private_scope(self):
        with self.assertRaises(generation_error):
            self.authority.read()
        self.assertEqual(self.authority.publish(None, mark(1)), publish_result.outcome_unknown)
        self.assertFalse(self.directory.exists())
        self.authority.provision()
        self.assertIsNone(self.authority.read())
        with self.assertRaises(FileExistsError):
            self.authority.provision()
        with self.assertRaises(generation_error):
            generation_authority(self.directory.parent, b"b" * 16).read()
        self.directory.parent.chmod(0o720)
        with self.assertRaises(generation_error):
            self.authority.read()
        self.directory.parent.chmod(0o700)
        self.directory.chmod(0o750)
        with self.assertRaises(generation_error):
            self.authority.read()
        self.directory.chmod(0o700)
        active = self.directory / "generation"
        active.chmod(0o640)
        with self.assertRaises(generation_error):
            self.authority.read()
        active.chmod(0o600)
        linked, linked_authority = self.setup_authority("linked")
        linked.symlink_to(self.directory, target_is_directory=True)
        with self.assertRaises(generation_error):
            linked_authority.read()
        self.assertIsNone(self.authority.read())

    def test_compare_full_record_and_validate_progression(self):
        self.start_authority(self.authority)
        self.assertEqual(self.authority.publish(mark(1, "b"), mark(2)), publish_result.conflict)
        self.assertEqual(self.authority.publish(mark(1, length=148), mark(2)), publish_result.conflict)
        self.assertEqual(self.authority.publish(None, mark(1)), publish_result.conflict)
        for expected, candidate in ((mark(1), mark(1)), (mark(1), mark(3)), (None, mark(2)),
                                    (mark(1), mark(2, realm=b"b" * 16)),
                                    (mark(1, realm=b"b" * 16), mark(2))):
            with self.subTest(expected=expected, candidate=candidate), self.assertRaises(ValueError):
                self.authority.publish(expected, candidate)
        for revision, length in ((0, 80), (True, 80), (-1, 80), (_max_revision + 1, 80),
                                 (1, 79), (1, 81), (1, 4500)):
            with self.subTest(revision=revision, length=length), self.assertRaises(ValueError):
                mark(revision, length=length)
        self.assertEqual(self.authority.publish(mark(1), mark(2, length=4432)), publish_result.committed)
        self.assertEqual(self.authority.publish(mark(1), mark(2)), publish_result.conflict)
        self.assertEqual(self.authority.read(), mark(2, length=4432))

    def test_saturated_record_cannot_wrap(self):
        self.start_authority(self.authority)
        # Set up the terminal revision directly, avoiding 2**64 writes.
        active = self.directory / "generation"
        fields = struct.pack("<8s16sQI32s", b"PUMGEN\0\1", _realm, _max_revision, 80, mark(_max_revision).checksum)
        active.write_bytes(fields + hashlib.sha256(fields).digest())
        self.assertEqual(self.authority.read(), mark(_max_revision))
        with self.assertRaises(ValueError):
            self.authority.publish(mark(_max_revision), mark(1))
        self.assertEqual(self.authority.read(), mark(_max_revision))

    def test_missing_malformed_or_redirected_record_fails_closed(self):
        self.start_authority(self.authority)
        active = self.directory / "generation"
        valid = active.read_bytes()
        wrong_tag = b"X" + valid[1:-32]
        wrong_realm = valid[:8] + b"b" * 16 + valid[24:-32]
        invalid_fields = struct.pack("<8s16sQI32s", b"PUMGEN\0\1", _realm, 0, 80, bytes(32))
        for broken in (b"", valid[:-1], valid + b"extra", b"X" + valid[1:],
                       wrong_tag + hashlib.sha256(wrong_tag).digest(),
                       wrong_realm + hashlib.sha256(wrong_realm).digest(),
                       invalid_fields + hashlib.sha256(invalid_fields).digest()):
            with self.subTest(size=len(broken)):
                active.write_bytes(broken)
                with self.assertRaises(generation_error):
                    self.authority.read()
                self.assertEqual(self.authority.publish(mark(1), mark(2)), publish_result.outcome_unknown)
                self.assertEqual(active.read_bytes(), broken)
        active.unlink()
        with self.assertRaises(generation_error):
            self.authority.read()
        self.assertEqual(self.authority.publish(None, mark(1)), publish_result.outcome_unknown)
        with self.assertRaises(FileExistsError):
            self.authority.provision()
        target = self.root / "other-record"
        target.write_bytes(valid)
        active.symlink_to(target)
        with self.assertRaises(generation_error):
            self.authority.read()
        self.assertEqual(target.read_bytes(), valid)

    def test_concurrent_writers_serialize_entire_comparison(self):
        self.start_authority(self.authority)
        with child("write", self.directory, "before_replace", "a") as first:
            self.assertEqual(line(first), "attempting")
            self.assertEqual(line(first), "paused")
            with child("write", self.directory, "replace", "b") as second:
                self.assertEqual(line(second), "attempting")
                self.assertEqual(select.select([second.stdout], [], [], 0.2)[0], [])
                first.stdin.write(b"release\n")
                self.assertEqual(line(first), "committed")
                self.assertEqual(line(second), "conflict")
                self.assertEqual(first.wait(timeout=10), 0)
                self.assertEqual(second.wait(timeout=10), 0)
        self.assert_fresh_read(self.directory, mark(2))

    def test_killed_process_boundaries_reopen_exact_record(self):
        for phase, revision in (("before_replace", 1), ("after_replace", 2), ("after_sync", 2)):
            with self.subTest(phase=phase):
                directory, authority = self.setup_authority(phase)
                self.start_authority(authority)
                with child("write", directory, phase) as process:
                    self.assertEqual(line(process), "attempting")
                    self.assertEqual(line(process), "paused")
                    process.kill()
                    self.assertEqual(process.wait(timeout=10), -signal.SIGKILL)
                self.assert_fresh_read(directory, mark(revision))
                if revision == 1:
                    self.assertTrue((directory / "pending").is_file())
                    self.assertEqual(authority.publish(mark(1), mark(2, "b")), publish_result.committed)
                    self.assertFalse((directory / "pending").exists())
                    self.assert_fresh_read(directory, mark(2, "b"))
                else:
                    self.assertEqual(authority.publish(mark(1), mark(2, "b")), publish_result.conflict)

    def test_sync_failure_classifies_known_and_unknown_outcomes(self):
        self.start_authority(self.authority)
        sync, replace = os.fsync, os.replace

        def fail_stage(descriptor):
            if stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise OSError("injected staged file sync failure")
            sync(descriptor)

        installed = False

        def track_install(*args, **kwargs):
            nonlocal installed
            replace(*args, **kwargs)
            installed = True

        def fail_after_install(descriptor):
            if installed:
                raise OSError("injected directory sync failure")
            sync(descriptor)

        with patch.object(os, "fsync", fail_stage):
            self.assertEqual(self.authority.publish(mark(1), mark(2)), publish_result.unchanged)
        self.assert_fresh_read(self.directory, mark(1))
        with patch.object(os, "replace", track_install), patch.object(os, "fsync", fail_after_install):
            self.assertEqual(self.authority.publish(mark(1), mark(2)), publish_result.outcome_unknown)
        self.assert_fresh_read(self.directory, mark(2))

    def test_replacing_disposable_snapshot_bytes_keeps_independent_record(self):
        self.authority.provision()
        image = self.root / "disposable-snapshot"

        def stage(data):
            with image.open("wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            self.assertEqual(image.read_bytes(), data)

        old, newest = empty_snapshot(1), empty_snapshot(2)
        old_mark = generation_mark(_realm, 1, len(old), old[-32:])
        newest_mark = generation_mark(_realm, 2, len(newest), newest[-32:])
        stage(old)
        self.assertEqual(self.authority.publish(None, old_mark), publish_result.committed)
        stage(newest)
        self.assertEqual(self.authority.publish(old_mark, newest_mark), publish_result.committed)
        stage(old)
        self.assert_fresh_read(self.directory, newest_mark)
        self.assertNotEqual(image.read_bytes()[-32:], self.authority.read().checksum)
        self.assertEqual(self.authority.publish(old_mark, newest_mark), publish_result.conflict)


if __name__ == "__main__":
    if sys.argv[1:2] == ["--child"]:
        child_main(*sys.argv[2:])
    else:
        unittest.main(verbosity=2)
