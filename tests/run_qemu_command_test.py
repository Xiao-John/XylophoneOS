#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Regression checks for QEMU's filter-dump property encoding."""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from run_qemu import qemu_command


class CaptureArgumentTest(unittest.TestCase):
    @patch("run_qemu.shutil.which", return_value="qemu-system-x86_64")
    def test_capture_path_is_a_single_qemu_property_value(self, _which):
        prefix = "filter-dump,id=xos_capture,netdev=xosnet,file="
        for name, encoded in (("review.pcap", "review.pcap"),
                              ("net,review.pcap", "net,,review.pcap"),
                              ("net,,review.pcap", "net,,,,review.pcap")):
            with self.subTest(name=name):
                command = qemu_command("boot.iso", iso=True, network=True,
                                       network_capture=Path(name))
                self.assertEqual(command[command.index("-object") + 1], prefix + encoded)


if __name__ == "__main__":
    unittest.main()
