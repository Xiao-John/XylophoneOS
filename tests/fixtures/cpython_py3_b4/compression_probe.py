# SPDX-License-Identifier: Apache-2.0
"""Bounded stream and malformed-input checks for PY3 B4 compression ports."""

import bz2
import lzma
from compression import zstd


PAYLOAD = (bytes(range(256)) + b"XOS compression keeps its cool.\n" * 71) * 4
CHUNK = 257


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def stream_roundtrip(compressor_type, decompressor_type, payload, *, flush=None):
    compressor = compressor_type()
    encoded = bytearray()
    for offset in range(0, len(payload), 193):
        encoded.extend(compressor.compress(payload[offset:offset + 193]))
    encoded.extend(compressor.flush() if flush is None else flush(compressor))

    decoder = decompressor_type()
    decoded = bytearray()
    largest = 0
    for offset in range(0, len(encoded), 43):
        source = bytes(encoded[offset:offset + 43])
        while True:
            part = decoder.decompress(source, max_length=CHUNK)
            source = b""
            largest = max(largest, len(part))
            decoded.extend(part)
            if decoder.eof or decoder.needs_input:
                break
    while not decoder.eof and not decoder.needs_input:
        part = decoder.decompress(b"", max_length=CHUNK)
        largest = max(largest, len(part))
        decoded.extend(part)
        require(part or decoder.eof or decoder.needs_input, "decoder made no progress")
    require(bytes(decoded) == payload, "stream roundtrip changed bytes")
    require(decoder.eof, "valid stream did not reach EOF")
    require(largest <= CHUNK, "decompressor exceeded max_length")
    return bytes(encoded), largest


def malformed_checks(decompress, decoder_type, encoded, truncated_error, corrupt_error):
    try:
        decompress(encoded[:-1])
    except truncated_error:
        pass
    except Exception as error:
        raise AssertionError(f"truncated stream raised unexpected {type(error).__name__}") from error
    # Truncation may produce a prefix without an error; the streaming decoder's
    # eof flag is the unambiguous indication that the frame completed.
    decoder = decoder_type()
    decoder.decompress(encoded[:-1])
    require(not decoder.eof, "truncated stream was reported complete")

    corrupted = bytearray(encoded)
    corrupted[len(corrupted) // 2] ^= 0x40
    try:
        decompress(bytes(corrupted))
    except corrupt_error:
        return
    except Exception as error:
        raise AssertionError(f"corrupt stream raised unexpected {type(error).__name__}") from error
    raise AssertionError("corrupt stream was accepted")


def run_bz2():
    encoded, largest = stream_roundtrip(bz2.BZ2Compressor, bz2.BZ2Decompressor, PAYLOAD)
    malformed_checks(bz2.decompress, bz2.BZ2Decompressor, encoded, ValueError, OSError)
    return {"roundtrip_bytes": len(PAYLOAD), "compressed_bytes": len(encoded), "max_output_chunk": largest}


def run_lzma():
    encoded, largest = stream_roundtrip(lzma.LZMACompressor, lzma.LZMADecompressor, PAYLOAD)
    malformed_checks(lzma.decompress, lzma.LZMADecompressor, encoded,
                     lzma.LZMAError, lzma.LZMAError)
    return {"roundtrip_bytes": len(PAYLOAD), "compressed_bytes": len(encoded), "max_output_chunk": largest}


def run_zstd():
    def finish(compressor):
        return compressor.flush(zstd.ZstdCompressor.FLUSH_FRAME)

    # Zstandard frames omit checksums by default; enable one so a deliberately
    # corrupted payload has a defined integrity failure to exercise.
    compressor_type = lambda: zstd.ZstdCompressor(
        options={zstd.CompressionParameter.checksum_flag: 1}
    )
    encoded, largest = stream_roundtrip(compressor_type, zstd.ZstdDecompressor,
                                        PAYLOAD, flush=finish)
    malformed_checks(zstd.decompress, zstd.ZstdDecompressor, encoded,
                     zstd.ZstdError, zstd.ZstdError)
    return {"roundtrip_bytes": len(PAYLOAD), "compressed_bytes": len(encoded), "max_output_chunk": largest}


def main():
    results = {
        "bz2": run_bz2(),
        "lzma": run_lzma(),
        "zstd": run_zstd(),
    }
    for name, result in results.items():
        print(f"PY3_B4_{name.upper()}_OK {result}")
    print("PY3_B4_OK")


if __name__ == "__main__":
    main()
