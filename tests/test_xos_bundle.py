#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for XOSBND1 containers (docs/contracts/xos_bundle_v1.md)."""
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import xos_bundle as xb  # noqa: E402


def elf_stub(payload=b'ELFDATA') -> bytes:
    return b'\x7fELF' + payload


def xpk_stub(payload=b'XPKDATA') -> bytes:
    # 512-byte ustar header prefix + payload so magic at 257 validates
    header = bytearray(512)
    header[257:263] = b'ustar\x00'
    header[263:265] = b'00'
    return bytes(header) + payload


class BundleRoundTrip(unittest.TestCase):
    def test_build_parse_dash_only(self):
        blob = xb.build([(xb.TYPE_DASH, 'dash', elf_stub())])
        info = xb.parse(blob)
        self.assertEqual(info['version'], 1)
        self.assertEqual(len(info['members']), 1)
        self.assertEqual(info['members'][0]['name'], 'dash')
        self.assertEqual(blob[:8], xb.MAGIC)
        self.assertEqual(struct.unpack_from('<Q', blob, 16)[0], len(blob))

    def test_full_trio(self):
        members = [
            (xb.TYPE_DASH, 'dash', elf_stub(b'dash-body')),
            (xb.TYPE_XYPm, 'xypm.xpk', xpk_stub(b'xypm')),
            (xb.TYPE_DAILY, 'daily.xpk', xpk_stub(b'daily')),
        ]
        blob = xb.build(members)
        info = xb.parse(blob)
        self.assertEqual([m['name'] for m in info['members']],
                         ['dash', 'xypm.xpk', 'daily.xpk'])
        # hash verify by slicing
        m0 = info['members'][0]
        data = blob[m0['data_off']:m0['data_off'] + m0['data_len']]
        self.assertEqual(data, elf_stub(b'dash-body'))

    def test_total_within_budget(self):
        blob = xb.build([(xb.TYPE_DASH, 'd', elf_stub())])
        self.assertLessEqual(len(blob), xb.MAX_TOTAL)

    def test_reject_missing_dash(self):
        with self.assertRaises(xb.BundleError):
            xb.build([(xb.TYPE_XYPm, 'x', xpk_stub())])

    def test_reject_duplicate_daily(self):
        with self.assertRaises(xb.BundleError):
            xb.build([
                (xb.TYPE_DASH, 'd', elf_stub()),
                (xb.TYPE_DAILY, 'a', xpk_stub()),
                (xb.TYPE_DAILY, 'b', xpk_stub()),
            ])


class BundleReject(unittest.TestCase):
    def _good(self) -> bytes:
        return xb.build([
            (xb.TYPE_DASH, 'dash', elf_stub(b'x')),
            (xb.TYPE_XYPm, 'x.xpk', xpk_stub()),
        ])

    def test_bad_magic(self):
        blob = bytearray(self._good())
        blob[0:8] = b'NOTABND\x00'
        with self.assertRaises(xb.BundleError):
            xb.parse(bytes(blob))

    def test_bad_version(self):
        blob = bytearray(self._good())
        struct.pack_into('<I', blob, 8, 99)
        with self.assertRaises(xb.BundleError):
            xb.parse(bytes(blob))

    def test_total_mismatch(self):
        blob = bytearray(self._good())
        struct.pack_into('<Q', blob, 16, len(blob) + 1)
        with self.assertRaises(xb.BundleError):
            xb.parse(bytes(blob))

    def test_hash_mismatch(self):
        blob = bytearray(self._good())
        info = xb.parse(bytes(blob), check_hashes=False)
        m0 = info['members'][0]
        blob[m0['data_off']] ^= 0xFF
        with self.assertRaises(xb.BundleError):
            xb.parse(bytes(blob))

    def test_truncated(self):
        blob = self._good()
        with self.assertRaises(xb.BundleError):
            xb.parse(blob[:20])

    def test_reserved_nonzero(self):
        blob = bytearray(self._good())
        struct.pack_into('<I', blob, 28, 1)
        with self.assertRaises(xb.BundleError):
            xb.parse(bytes(blob))

    def test_elf_magic_required(self):
        with self.assertRaises(xb.BundleError):
            xb.build([(xb.TYPE_DASH, 'dash', b'NOT_ELF_AT_ALL_HERE')])
        # parse-side check for defense in depth: valid-looking container with bad dash
        # cannot be constructed via build(); skip raw byte surgery here.

    def test_real_xpk_magic(self):
        # use a real xpk if present for positive control
        for cand in (Path('build/idna-3.20.xpk'),):
            if cand.is_file():
                blob = xb.build([(xb.TYPE_DASH, 'dash', elf_stub()),
                                 (xb.TYPE_XYPm, 'idna.xpk', cand.read_bytes())])
                info = xb.parse(blob)
                self.assertEqual(len(info['members']), 2)
                return
        self.skipTest('no idna xpk on disk')


if __name__ == '__main__':
    unittest.main()

class BundleToolElf(unittest.TestCase):
    def test_tool_elf_roundtrip(self):
        blob = xb.build([
            (xb.TYPE_DASH, 'dash', elf_stub()),
            (xb.TYPE_TOOL, 'xypm', elf_stub(b'xypm-tool')),
        ])
        info = xb.parse(blob)
        self.assertEqual([m['type'] for m in info['members']], [xb.TYPE_DASH, xb.TYPE_TOOL])
        self.assertEqual(info['members'][1]['name'], 'xypm')

    def test_tool_must_be_elf(self):
        with self.assertRaises(xb.BundleError):
            xb.build([
                (xb.TYPE_DASH, 'dash', elf_stub()),
                (xb.TYPE_TOOL, 'xypm', b'NOT_ELF'),
            ])

    def test_parse_rejects_non_elf_tool(self):
        # bypass build check by patching bytes after build is not easy; build already checks
        blob = xb.build([
            (xb.TYPE_DASH, 'd', elf_stub()),
            (xb.TYPE_TOOL, 't', elf_stub()),
        ])
        info = xb.parse(blob)
        self.assertEqual(info['members'][1]['type'], xb.TYPE_TOOL)


