# SPDX-License-Identifier: Apache-2.0
"""Read Qt 6 rcc payloads from retained ELF relocatable archive members."""

import hashlib
import struct
import zlib


def section_payloads(elf):
    if len(elf) < 64 or elf[:7] != b"\x7fELF\x02\x01\x01" or struct.unpack_from("<H", elf, 16) != (1,):
        raise ValueError("Expected a little-endian ELF64 relocatable object")
    begin = struct.unpack_from("<Q", elf, 40)[0]
    size, count = struct.unpack_from("<HH", elf, 58)
    section_header = struct.Struct("<IIQQQQIIQQ")
    if not (size == section_header.size and count > 0 and begin + size * count <= len(elf)):
        raise ValueError("Invalid ELF section header table")
    headers = [section_header.unpack_from(elf, begin + size * index) for index in range(count)]
    symbol = struct.Struct("<IBBHQQ")
    sections = {}
    for _, kind, _, _, offset, length, link, _, _, entry_size in headers:
        if kind != 2:  # SHT_SYMTAB
            continue
        if entry_size != symbol.size or length % entry_size or link >= count or headers[link][1] != 3:
            raise ValueError("Invalid ELF symbol table")
        _, _, _, _, string_offset, string_size, *_ = headers[link]
        names = read_bytes(elf, string_offset, string_size)
        for name, info, _, index, value, data_size in symbol.iter_unpack(read_bytes(elf, offset, length)):
            if info & 15 != 1:
                continue
            end = names.find(b"\0", name)
            if end < name:
                raise ValueError("Invalid ELF symbol name")
            for part in ("data", "name", "struct"):
                if not names[name:end].endswith(b"qt_resource_" + part.encode()):
                    continue
                if part in sections or index >= count or value + data_size > headers[index][5]:
                    raise ValueError("Invalid resource symbol range")
                sections[part] = read_bytes(elf, headers[index][4] + value, data_size)
    if sections.keys() != {"data", "name", "struct"}:
        raise ValueError("The rcc object lacks the expected Qt resource sections")
    return sections


def read_bytes(blob, offset, size):
    if not (0 <= offset <= offset + size <= len(blob)):
        raise ValueError("Resource payload points outside its input")
    return blob[offset:offset + size]


def embedded_resources(elf):
    sections = section_payloads(elf)
    tree, names, data = (sections[key] for key in ("struct", "name", "data"))
    # Qt resource format 2/3 adds an eight-byte last-modified field per tree node.
    node_bytes = 22
    if len(tree) % node_bytes or not tree:
        raise ValueError("Expected a Qt rcc format 2/3 resource tree")
    entries = {}
    pending = [(0, "")]
    visited = set()
    while pending:
        index, parent = pending.pop()
        if index in visited:
            raise ValueError("Resource tree references a node more than once")
        visited.add(index)
        node = read_bytes(tree, index * node_bytes, node_bytes)
        offset, flags = struct.unpack_from(">IH", node)
        if index == 0 and flags != 2:
            raise ValueError("Qt resource root is not a directory")
        if index:
            count = struct.unpack(">H", read_bytes(names, offset, 2))[0]
            name = read_bytes(names, offset + 6, count * 2).decode("utf-16-be")
            if not name or "/" in name or name in {".", ".."}:
                raise ValueError("Invalid resource name")
            path = parent + "/" + name
        else:
            path = parent
        if flags == 2:
            count, child = struct.unpack_from(">II", node, 6)
            if child + count > len(tree) // node_bytes:
                raise ValueError("Resource directory points outside the tree")
            pending.extend((number, path) for number in range(child, child + count))
            continue
        if flags not in (0, 1):
            raise ValueError("Unsupported compression or flag in the captured rcc object")
        territory, language, offset = struct.unpack_from(">HHI", node, 6)
        length = struct.unpack(">I", read_bytes(data, offset, 4))[0]
        payload = read_bytes(data, offset + 4, length)
        if flags == 1:
            decoded_length = struct.unpack(">I", read_bytes(payload, 0, 4))[0]
            payload = zlib.decompress(payload[4:])
            if len(payload) != decoded_length:
                raise ValueError("Invalid uncompressed resource length")
        if path in entries:
            raise ValueError("Localized duplicate resources require an explicit locale map")
        entries[path] = {"sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload),
                         "territory": territory, "language": language, "zlib": flags == 1}
    if len(visited) != len(tree) // node_bytes:
        raise ValueError("Resource tree contains an unreachable node")
    return entries
