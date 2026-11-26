#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Restore the published QtBase 6.8.3 fragment binding order in a rebuilt QSB v6 pack."""

import argparse
from pathlib import Path
import struct
import zlib


def restore_binding_order(data):
    # QShader v6 ends with a native resource map count, followed by two maps,
    # and the count for separate-to-combined images. Each native map starts
    # with its four-word shader key, entry count, and two binding triples.
    binding_tail = struct.Struct(">24i")
    if len(data) <= 4:
        raise ValueError("Truncated QSB pack")
    size, = struct.unpack_from(">I", data)
    payload = zlib.decompress(data[4:])
    if len(payload) != size or len(payload) <= binding_tail.size or struct.unpack_from(">II", payload) != (6, 4):
        raise ValueError("Expected the Qt backingstore fragment shader in QSB v6 format")
    tail = list(binding_tail.unpack(payload[-binding_tail.size:]))
    if tail[0] != 2 or tail[-1] != 0:
        raise ValueError("Unexpected Qt backingstore resource map shape")

    for offset, shader_key in ((1, [2, 50, 0, 0]), (12, [4, 12, 0, 0])):
        if tail[offset:offset + 5] != [*shader_key, 2]:
            raise ValueError("Expected two standard HLSL/MSL native resource bindings")
        begin = offset + 5
        first, second = tail[begin:begin + 3], tail[begin + 3:begin + 6]
        if {first[0], second[0]} != {0, 1}:
            raise ValueError("Expected the compositor uniform and sampler bindings")
        # The QtBase release serialized this pair with binding 1 preceding 0.
        if first[0] == 0:
            tail[begin:begin + 6] = [*second, *first]

    payload = payload[:-binding_tail.size] + binding_tail.pack(*tail)
    return struct.pack(">I", size) + zlib.compress(payload)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = restore_binding_order(args.source.read_bytes())
    with args.output.open("xb") as output:
        output.write(result)


if __name__ == "__main__":
    main()
