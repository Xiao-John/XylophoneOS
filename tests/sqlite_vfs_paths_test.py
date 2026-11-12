# SPDX-License-Identifier: Apache-2.0
"""Host-test the XOS VFS with the pinned, unmodified SQLite amalgamation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile

repo_root = Path(__file__).resolve().parents[1]
port_root = repo_root / "src/ports/cpython/sqlite"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path,
                        default=repo_root / ".cache/xos_seed/cpython/sqlite/sqlite-autoconf-3540100.tar.gz")
    parser.add_argument("--vfs", type=Path, default=port_root / "xos_vfs.c")
    args = parser.parse_args()
    lock = json.loads((port_root / "sqlite_lock.json").read_text())
    data = args.archive.read_bytes()
    assert len(data) == lock["archive_bytes"]
    for algorithm in ("sha256", "sha3_256"):
        assert hashlib.new(algorithm, data).hexdigest() == lock[algorithm]
    with tempfile.TemporaryDirectory(prefix="xos_sqlite_vfs_") as temporary:
        directory = Path(temporary)
        with tarfile.open(args.archive, "r:gz") as archive:
            for name in ("sqlite3.h", "sqlite3.c"):
                member = next(item for item in archive.getmembers() if item.name.endswith("/" + name))
                with archive.extractfile(member) as stream:
                    (directory / name).write_bytes(stream.read())
        binary = directory / "sqlite_vfs_paths_test"
        subprocess.run([
            os.environ.get("CC", "cc"), "-std=c99", "-D_DEFAULT_SOURCE", "-O0",
            "-DSQLITE_OS_OTHER=1", "-DSQLITE_THREADSAFE=0", "-DSQLITE_OMIT_LOAD_EXTENSION=1",
            "-DSQLITE_OMIT_WAL=1", "-DSQLITE_TEMP_STORE=3", "-DSQLITE_DQS=0",
            "-I", str(directory), str(directory / "sqlite3.c"), str(args.vfs.resolve()),
            str(repo_root / "tests/sqlite_vfs_paths_test.c"), "-o", str(binary),
        ], check=True)
        subprocess.run([str(binary)], cwd=directory, check=True)


if __name__ == "__main__":
    main()
