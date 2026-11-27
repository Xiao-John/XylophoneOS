#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Interrupt marker publication and verify the maintenance state can be reopened."""

from dataclasses import replace
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pumpkin_user_login as login


class ImageMaintenance(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.state = Path(temporary.name)
        self.marker = self.state / login.deployment_marker
        self.previous = SimpleNamespace(sha256="19" * 32, system_manifest_sha256="aa" * 32)
        self.replacement = SimpleNamespace(sha256="37" * 32, system_manifest_sha256="bb" * 32)
        self.old = self.previous.sha256.encode()
        self.new = login.active_binding(self.replacement)
        self.generation = login.generation_mark(b"x" * 16, 3, 80, b"k" * 32)
        self.disk = self.state / "work.img"
        self.disk.write_bytes(b"unchanged private guest disk fixture")
        self.marker.write_bytes(self.old)
        self.marker.chmod(0o600)
        for name in ("verify_update_roles", "verify_update_pair", "verify_update_image"):
            context = patch.object(login, name)
            context.start()
            self.addCleanup(context.stop)
        context = patch.object(login, "provider_client", side_effect=self.provider)
        context.start()
        self.addCleanup(context.stop)

    def provider(self, profile):
        return SimpleNamespace(read=lambda: self.generation)

    def update(self, command):
        return login.maintain_image(command, self.state, None, self.previous, None, self.replacement)["status"]

    def interrupt(self, command, *, after_rename):
        replace_marker = os.replace
        child = os.fork()
        if child == 0:
            def crash(old, new, **directory):
                if after_rename:
                    replace_marker(old, new, **directory)
                os._exit(81)

            try:
                with patch.object(login.os, "replace", side_effect=crash):
                    self.update(command)
            except BaseException:
                os._exit(82)
            os._exit(83)
        _, status = os.waitpid(child, 0)
        self.assertTrue(os.WIFEXITED(status))
        self.assertEqual(os.WEXITSTATUS(status), 81)
        self.assertEqual(self.disk.read_bytes(), b"unchanged private guest disk fixture")

    def assert_launch_fenced(self):
        for profile in (self.previous, self.replacement):
            with self.subTest(profile=profile.sha256), self.assertRaisesRegex(
                    login.login_error, "image maintenance is in progress"):
                with login.locked_installation(self.state, profile):
                    self.fail("A boot was admitted while the marker was pending")

    def test_death_before_preparation_rename_leaves_previous_binding(self):
        self.interrupt(login.begin_image_command, after_rename=False)
        self.assertEqual(self.marker.read_bytes(), self.old)
        self.assertEqual(self.update(login.begin_image_command), "image_update_pending")
        self.assert_launch_fenced()

    def test_death_after_preparation_rename_fences_both_and_retry_preserves_record(self):
        self.interrupt(login.begin_image_command, after_rename=True)
        self.assert_launch_fenced()
        original = self.marker.read_bytes()
        self.assertEqual(self.update(login.begin_image_command), "image_update_pending")
        self.assertEqual(self.marker.read_bytes(), original)

    def test_death_before_activation_rename_keeps_pending_and_can_finish(self):
        self.update(login.begin_image_command)
        original = self.marker.read_bytes()
        self.interrupt(login.finish_image_command, after_rename=False)
        self.assertEqual(self.marker.read_bytes(), original)
        self.assert_launch_fenced()
        self.assertEqual(self.update(login.finish_image_command), "image_update_activated")
        self.assertEqual(self.marker.read_bytes(), self.new)

    def test_death_after_activation_rename_can_reconfirm_the_active_profile(self):
        self.update(login.begin_image_command)
        self.interrupt(login.finish_image_command, after_rename=True)
        self.assertEqual(self.marker.read_bytes(), self.new)
        self.assertEqual(self.update(login.finish_image_command), "image_binding_already_active")

    def test_ordinary_launch_fails_before_guest_start_when_binding_sync_fails(self):
        binding = ("unused-build", "aa" * 32, {})
        with (patch.object(login, "bind_system", return_value=binding),
              patch.object(login, "select_deployment", return_value=False),
              patch.object(login.os, "fsync", side_effect=OSError("directory sync failed")),
              patch.object(login, "boot") as boot, self.assertRaisesRegex(OSError, "directory sync failed")):
            login.operate(None, self.state, "login", None, deployment=self.previous)
        boot.assert_not_called()

    def test_equal_revision_with_different_digest_refuses_activation_and_cancellation(self):
        self.update(login.begin_image_command)
        original = self.marker.read_bytes()
        self.generation = replace(self.generation, checksum=b"q" * 32)
        for command in (login.finish_image_command, login.cancel_image_command):
            with self.subTest(command=command), self.assertRaisesRegex(login.login_error, "generation changed"):
                self.update(command)
        self.assertEqual(self.marker.read_bytes(), original)
        self.assert_launch_fenced()

    def test_corrupt_pending_record_and_other_pair_fail_closed(self):
        self.update(login.begin_image_command)
        original = self.marker.read_bytes()
        self.replacement.sha256 = "82" * 32
        with self.assertRaisesRegex(login.login_error, "different deployment pair"):
            self.update(login.finish_image_command)
        self.replacement.sha256 = "37" * 32
        corrupt = original[:-1] + bytes([original[-1] ^ 1])
        self.marker.write_bytes(corrupt)
        with self.assertRaisesRegex(login.login_error, "no valid pending image update"):
            self.update(login.cancel_image_command)
        self.assertEqual(self.marker.read_bytes(), corrupt)
        self.assert_launch_fenced()


if __name__ == "__main__":
    unittest.main()
