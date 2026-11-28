#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Create native identity notes and bounded generation records from actual ELF bytes."""
import hashlib
import json
from pathlib import Path
import struct

INTERPRETER = '/usr/lib/xos/glibc_dynamic_v1/ld_xos_x86_64.so.1'
HEAP_BASE = 0x1fff00000000


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def identity(abi, role):
    abi = bytes.fromhex(abi) if isinstance(abi, str) else abi
    if len(abi) != 32 or not any(abi) or role not in (1, 2, 3, 4):
        raise ValueError('invalid native identity')
    return struct.pack('<Q10IQ32s40s', 0x31594e44534f5858, 1, 128, role, 62,
                       1, 1, 1, 1, 2, 1, 1, abi, bytes(40))


def write_note(path, abi, role):
    record = identity(abi, role)
    Path(path).write_text('.section .note.xos,"a",@note\n.balign 4\n'
        '.long 4,128,0x584f5301\n.asciz "XOS"\n.byte '
        + ','.join(map(str, record)) + '\n.section .note.GNU-stack,"",@progbits\n')


def elf_metadata(path):
    data = Path(path).read_bytes()
    if len(data) < 64 or data[:7] != b'\x7fELF\x02\x01\x01' or data[7] not in (0, 3):
        raise ValueError('not a supported ELF64 object')
    phoff = struct.unpack_from('<Q', data, 32)[0]
    phentsize, phnum = struct.unpack_from('<HH', data, 54)
    if phentsize != 56 or not 0 < phnum <= 64 or phoff + 56 * phnum > len(data):
        raise ValueError('invalid ELF program headers')
    programs = [struct.unpack_from('<IIQQQQQQ', data, phoff + i * 56) for i in range(phnum)]
    loads = [p for p in programs if p[0] == 1]
    notes = []
    for program in programs:
        if program[0] != 4:
            continue
        at, end = program[2], program[2] + program[5]
        while at < end:
            if at + 12 > end or end > len(data):
                raise ValueError('truncated ELF note')
            namesz, descsz, kind = struct.unpack_from('<III', data, at)
            descriptor = at + 12 + ((namesz + 3) & -4)
            next_note = descriptor + ((descsz + 3) & -4)
            if next_note > end:
                raise ValueError('truncated ELF note payload')
            if data[at + 12:at + 12 + namesz] == b'XOS\0' and kind == 0x584f5301:
                notes.append(data[descriptor:descriptor + descsz])
            at = next_note
    if len(notes) != 1 or len(notes[0]) != 128:
        raise ValueError('exactly one native identity note is required: ' + str(path))

    def memory(address, length):
        for p in loads:
            if p[3] <= address and address + length <= p[3] + p[5]:
                start = p[2] + address - p[3]
                return data[start:start + length]
        raise ValueError('ELF metadata outside file-backed LOAD')

    dynamic = []
    for p in programs:
        if p[0] == 2:
            for at in range(p[2], p[2] + p[5], 16):
                tag, value = struct.unpack_from('<QQ', data, at)
                if tag == 0:
                    break
                dynamic.append((tag, value))
    tags = dict(dynamic)
    strings = memory(tags[5], tags[10]) if dynamic else b''

    def string(offset):
        end = strings.find(b'\0', offset)
        if end < 0:
            raise ValueError('unterminated dynamic string')
        return strings[offset:end].decode('ascii')

    return {'path': str(path), 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
            'identity': notes[0], 'needed': [string(v) for t, v in dynamic if t == 1],
            'soname': string(tags[14]) if 14 in tags else '',
            'span': max((p[3] + p[6] + 4095) & -4096 for p in loads),
            'programs': programs}


def generation_record(generation_id, sdk_sha256, abi, entries, *, online_sonames=()):
    """entries are explicit (local ELF path, absolute guest path) in role order."""
    if not 4 <= len(entries) <= 12 or not 0 < generation_id < 2**64:
        raise ValueError('generation size or identity out of range')
    objects = [elf_metadata(path) for path, _ in entries]
    names = {obj['soname']: i for i, obj in enumerate(objects) if obj['soname']}
    if len(set(online_sonames)) != len(online_sonames) or any(name not in names for name in online_sonames):
        raise ValueError('online objects must name distinct approved libraries')
    online_mask = sum(1 << names[name] for name in online_sonames)
    if online_mask & 7:
        raise ValueError('only library objects can be online roots')
    records, total, mapped = [], 0, 0
    for index, ((_, path), obj) in enumerate(zip(entries, objects)):
        role = index + 1 if index < 3 else 4
        if obj['identity'] != identity(abi, role):
            raise ValueError('object belongs to a different native profile or role')
        if index == 1 and path != INTERPRETER:
            raise ValueError('interpreter must use the canonical native path')
        if index in (0, 2) and obj['soname']:
            raise ValueError('bootstrap and main cannot declare a SONAME')
        if len(path.encode()) >= 128 or len(obj['soname'].encode()) >= 128:
            raise ValueError('native object name exceeds the profile bound')
        edges = [names[name] for name in obj['needed']]
        if len(edges) > 12 or any(i in (0, 2, index) for i in edges):
            raise ValueError('invalid closed dependency graph')
        bias = 0 if index == 0 else 0x140000000000 + index * 0x02000000
        span = 0 if index == 0 else obj['span']
        if obj['size'] > 16 * 1024 * 1024 or span > 0x02000000 or bias + span >= HEAP_BASE:
            raise ValueError('object exceeds a native file or mapping bound')
        records.append(struct.pack('<Q32s128sQQI12s128s128s56s', obj['size'],
            bytes.fromhex(obj['sha256']), obj['identity'], bias, span, len(edges), bytes(edges),
            obj['soname'].encode(), path.encode(), bytes(56)))
        total += obj['size']
        mapped += span
        if online_mask & (1 << index):
            mapped += span
    if total > 64 * 1024 * 1024 or mapped > 128 * 1024 * 1024:
        raise ValueError('closure exceeds the native aggregate bound')
    header = struct.pack('<QIIQII32s32sQQQQ', 0x314e4547534f5858, 2 if online_mask else 1, 128 + len(records) * 512,
        generation_id, len(records), online_mask, bytes.fromhex(sdk_sha256), bytes.fromhex(abi), total, mapped,
        30_000_000_000, 0)
    return header + b''.join(records), objects
