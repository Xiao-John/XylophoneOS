#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build and validate XOSBND1 boot payload containers (docs/contracts/xos_bundle_v1.md)."""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

MAGIC = b'XOSBND1\x00'
VERSION = 1
HEADER_SIZE = 64
ENTRY_SIZE = 64
MAX_MEMBERS = 16
MAX_NAMES = 2048
MAX_TOTAL = 33554432  # iso_payload_max_bytes
MAX_NAME = 127

TYPE_DASH = 1
TYPE_XYPm = 2
TYPE_DAILY = 3
TYPE_AUX = 4
TYPE_TOOL = 5


class BundleError(ValueError):
    pass


def _sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _check_name(name: str) -> bytes:
    raw = name.encode('utf-8')
    if not (1 <= len(raw) <= MAX_NAME):
        raise BundleError(f'name length out of range: {name!r}')
    for b in raw:
        if b < 0x20 or b > 0x7e or b in (0x2f,):
            raise BundleError(f'invalid name byte in {name!r}')
    return raw


def build(members, total_align=4) -> bytes:
    """members: list of (type:int, name:str, data:bytes). Returns container bytes."""
    if not (1 <= len(members) <= MAX_MEMBERS):
        raise BundleError('member_count out of range')
    names = bytearray()
    name_spans = {}
    for typ, name, data in members:
        raw = _check_name(name)
        if name in name_spans:
            raise BundleError(f'duplicate name: {name}')
        if len(data) < 1:
            raise BundleError(f'empty data: {name}')
        if typ in (TYPE_DASH, TYPE_TOOL) and data[:4] != b'\x7fELF':
            raise BundleError(f'type {typ} is not ELF: {name}')
        name_spans[name] = (len(names), len(raw))
        names += raw
    if len(names) > MAX_NAMES:
        raise BundleError('names_bytes exceeds limit')

    types = [m[0] for m in members]
    if types.count(TYPE_DASH) != 1:
        raise BundleError('exactly one dash_elf required')
    if types.count(TYPE_XYPm) > 1 or types.count(TYPE_DAILY) > 1:
        raise BundleError('bootstrap_xypm/daily_tools_xpk at most one')

    header_and_entries = HEADER_SIZE + ENTRY_SIZE * len(members)
    names_off = header_and_entries
    data_start = names_off + len(names)
    head_pad = (-data_start) % total_align
    data_start += head_pad

    entries = []
    cursor = data_start
    blobs = bytearray()
    for typ, name, data in members:
        noff, nlen = name_spans[name]
        digest = _sha256(data)
        entries.append(struct.pack('<IIIIQQ', typ, noff, nlen, 0, cursor, len(data)) + digest)
        blobs += data
        cursor += len(data)
        # keep every subsequent data_off 4-aligned
        gap = (-cursor) % total_align
        if gap:
            blobs += b'\x00' * gap
            cursor += gap

    total = data_start + len(blobs)
    if total > MAX_TOTAL:
        raise BundleError(f'total_bytes {total} exceeds {MAX_TOTAL}')

    header = struct.pack(
        '<8sIIQII16s16s',
        MAGIC, VERSION, len(members), total, len(names),
        0, b'\x00' * 16, b'\x00' * 16,
    )
    assert len(header) == HEADER_SIZE, len(header)
    out = header + b''.join(entries) + bytes(names) + (b'\x00' * head_pad) + bytes(blobs)
    assert len(out) == total
    return out


def parse(blob: bytes, *, check_hashes=True, check_magic_bytes=True) -> dict:
    """Validate and return {'members': [{'type','name','data_off','data_len','sha256'}], ...}."""
    if len(blob) < HEADER_SIZE:
        raise BundleError('truncated header')
    magic, version, count, total, names_bytes, reserved0, r1, r2 = struct.unpack_from(
        '<8sIIQII16s16s', blob, 0)
    if magic != MAGIC:
        raise BundleError('bad magic')
    if version != VERSION:
        raise BundleError(f'unknown version {version}')
    if not (1 <= count <= MAX_MEMBERS):
        raise BundleError('member_count out of range')
    if total != len(blob):
        raise BundleError(f'total_bytes {total} != file size {len(blob)}')
    if total > MAX_TOTAL:
        raise BundleError('total exceeds 32MiB budget')
    if names_bytes > MAX_NAMES:
        raise BundleError('names_bytes exceeds limit')
    if reserved0 != 0 or r1 != b'\x00' * 16 or r2 != b'\x00' * 16:
        raise BundleError('reserved fields must be zero')

    entries_off = HEADER_SIZE
    entries_end = entries_off + ENTRY_SIZE * count
    if entries_end > len(blob):
        raise BundleError('entries truncated')
    names_off = entries_end
    names_end = names_off + names_bytes
    if names_end > len(blob):
        raise BundleError('names truncated')
    names_blob = blob[names_off:names_end]

    members = []
    types = []
    spans = []
    for i in range(count):
        typ, noff, nlen, reserved, doff, dlen = struct.unpack_from(
            '<IIIIQQ', blob, entries_off + i * ENTRY_SIZE)
        digest = blob[entries_off + i * ENTRY_SIZE + 32:entries_off + i * ENTRY_SIZE + 64]
        if reserved != 0:
            raise BundleError(f'entry {i} reserved must be 0')
        if typ not in (TYPE_DASH, TYPE_XYPm, TYPE_DAILY, TYPE_AUX, TYPE_TOOL):
            raise BundleError(f'unknown type {typ}')
        if not (1 <= nlen <= MAX_NAME) or noff + nlen > names_bytes:
            raise BundleError(f'entry {i} name out of range')
        name = names_blob[noff:noff + nlen]
        if any(b < 0x20 or b > 0x7e or b == 0x2f for b in name):
            raise BundleError(f'entry {i} invalid name bytes')
        try:
            name_s = name.decode('ascii')
        except UnicodeDecodeError as e:
            raise BundleError(f'entry {i} name not ascii') from e
        if dlen < 1 or doff + dlen > total or doff < names_end:
            raise BundleError(f'entry {i} data range invalid')
        if doff % 4 != 0:
            raise BundleError(f'entry {i} data_off not 4-aligned')
        # gap before data region must be zero — checked loosely via first data_off
        if doff + dlen > total:
            raise BundleError(f'entry {i} past end')
        members.append({
            'type': typ, 'name': name_s, 'data_off': doff, 'data_len': dlen,
            'sha256': digest,
        })
        types.append(typ)
        spans.append((doff, doff + dlen))

    # zero padding between names_end and first data_off
    first_data = min(s[0] for s in spans)
    if any(b != 0 for b in blob[names_end:first_data]):
        raise BundleError('non-zero alignment padding')
    # overlap
    spans_sorted = sorted(spans)
    for a, b in zip(spans_sorted, spans_sorted[1:]):
        if b[0] < a[1]:
            raise BundleError('member data regions overlap')

    if types.count(TYPE_DASH) != 1:
        raise BundleError('exactly one dash_elf required')
    if types.count(TYPE_XYPm) > 1 or types.count(TYPE_DAILY) > 1:
        raise BundleError('duplicate bootstrap/daily type')

    seen_names = set()
    for m in members:
        if m['name'] in seen_names:
            raise BundleError('duplicate member name')
        seen_names.add(m['name'])
        data = blob[m['data_off']:m['data_off'] + m['data_len']]
        if check_hashes and _sha256(data) != m['sha256']:
            raise BundleError(f"sha256 mismatch: {m['name']}")
        if check_magic_bytes:
            if m['type'] in (TYPE_DASH, TYPE_TOOL):
                if data[:4] != b'\x7fELF':
                    raise BundleError(f"type {m['type']} is not ELF: {m['name']}")
            else:
                # xpk v1: POSIX ustar magic at offset 257 of the first header
                if len(data) < 263 or data[257:263] != b'ustar\x00':
                    raise BundleError(f"xpk missing ustar magic: {m['name']}")

    return {
        'version': version,
        'total_bytes': total,
        'members': members,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('build', help='assemble container from members')
    b.add_argument('-o', '--output', type=Path, required=True)
    b.add_argument('--manifest', type=Path, required=True,
                   help='JSON list: [{"type":1,"name":"dash","path":"..."}]')
    v = sub.add_parser('verify', help='validate an existing container')
    v.add_argument('container', type=Path)
    v.add_argument('--json', action='store_true')
    args = parser.parse_args()

    try:
        if args.cmd == 'build':
            spec = json.loads(args.manifest.read_text())
            members = []
            for item in spec:
                data = Path(item['path']).read_bytes()
                members.append((int(item['type']), item['name'], data))
            blob = build(members)
            args.output.write_bytes(blob)
            info = parse(blob)
            print(json.dumps({
                'output': str(args.output), 'bytes': len(blob),
                'members': [{'type': m['type'], 'name': m['name'],
                             'data_len': m['data_len']} for m in info['members']],
            }, indent=2))
        else:
            blob = args.container.read_bytes()
            info = parse(blob)
            if args.json:
                print(json.dumps(info, default=lambda o: o.hex() if isinstance(o, bytes) else o,
                                 indent=2))
            else:
                print(f'OK version={info["version"]} bytes={info["total_bytes"]}')
                for m in info['members']:
                    print(f'  type={m["type"]} {m["name"]} len={m["data_len"]} sha={m["sha256"].hex()[:16]}…')
    except BundleError as e:
        print(f'REJECT: {e}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
