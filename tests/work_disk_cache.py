# SPDX-License-Identifier: Apache-2.0
"""The work-disk host tool cache must verify the binary hash, not only sources."""
import hashlib
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import work_disk  # noqa: E402


def main():
    with tempfile.TemporaryDirectory(prefix="xos_work_disk_cache_") as folder:
        folder = Path(folder)
        output = folder / "work_disk_host"
        stamp = folder / "work_disk_host.sha256"
        binary = b"compiled-helper"
        output.write_bytes(binary)
        digest = hashlib.sha256(binary).hexdigest()
        stamp.write_text("sources\n" + digest + "\n")
        assert work_disk._cache_valid(output, stamp, "sources")
        stamp.write_text("sources\n" + ("0" * 64) + "\n")
        assert not work_disk._cache_valid(output, stamp, "sources")
        stamp.write_text("other-sources\n" + digest + "\n")
        assert not work_disk._cache_valid(output, stamp, "sources")
        stamp.write_text("sources\n" + digest + "\n")
        link = folder / "link"
        link.symlink_to(output)
        assert not work_disk._cache_valid(link, stamp, "sources")
        # corrupt (non-UTF-8) stamp bytes must read as an invalid cache, not raise
        stamp.write_bytes(b"\xff\xfe\x00\x80broken-utf8")
        assert not work_disk._cache_valid(output, stamp, "sources")
        # '\' is a FatFs separator: transfer must reject it before any tool runs
        image = folder / "disk.img"
        image.write_bytes(b"fake-image-bytes")
        original_host_tool = work_disk.host_tool

        def _no_host_tool(*_args, **_kwargs):
            raise AssertionError("host_tool must not run for a rejected path")

        work_disk.host_tool = _no_host_tool
        try:
            for bad_path in (r"/safe\sub\XOSBAK.TMP", "/dir\\file.txt"):
                try:
                    work_disk.transfer(image, "mkdir", bad_path)
                except ValueError:
                    pass
                else:
                    raise AssertionError(f"backslash path accepted: {bad_path!r}")
        finally:
            work_disk.host_tool = original_host_tool
        assert image.read_bytes() == b"fake-image-bytes"
        # a corrupt stamp makes host_tool rebuild through the temp tree, not build/
        tree = folder / "tree"
        (tree / "scripts").mkdir(parents=True)
        (tree / "src/third_party/fatfs").mkdir(parents=True)
        (tree / "src/user/services").mkdir(parents=True)
        (tree / "build").mkdir(parents=True)
        (tree / "scripts/work_disk_host.cpp").write_text("// stub\n")
        (tree / "src/third_party/fatfs/ff.c").write_text("/* stub */\n")
        (tree / "src/third_party/fatfs/ff.h").write_text("/* stub */\n")
        (tree / "src/user/services/fatfs_unicode.cpp").write_text("// stub\n")
        (tree / "build/work_disk_host.sha256").write_bytes(b"\xff\xfe\x00broken")

        def _fake_compile(command, check):
            Path(command[command.index("-o") + 1]).write_bytes(b"rebuilt-helper")

        real_root = work_disk.ROOT
        real_run = work_disk.subprocess.run
        work_disk.ROOT = tree
        work_disk.subprocess.run = _fake_compile
        try:
            rebuilt = work_disk.host_tool()
        finally:
            work_disk.ROOT = real_root
            work_disk.subprocess.run = real_run
        assert rebuilt.read_bytes() == b"rebuilt-helper"
        sources = [tree / "scripts/work_disk_host.cpp",
                   tree / "src/third_party/fatfs/ff.c",
                   tree / "src/user/services/fatfs_unicode.cpp"]
        headers = list((tree / "src/third_party/fatfs").glob("*.h"))
        tree_digest = hashlib.sha256(b"".join(p.read_bytes() for p in sources + sorted(headers))).hexdigest()
        assert work_disk._cache_valid(rebuilt, rebuilt.with_suffix(".sha256"), tree_digest)
    print("WORK_DISK_CACHE_OK")


if __name__ == "__main__":
    main()
