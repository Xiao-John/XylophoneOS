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
    print("WORK_DISK_CACHE_OK")


if __name__ == "__main__":
    main()
