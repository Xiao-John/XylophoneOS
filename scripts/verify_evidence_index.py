#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify a report's file hashes in a checkout or one historical Git commit.

Supported indexes are SHA256SUMS files and JSON objects containing a path map,
or a map under ``files`` or ``evidence_sha256``. Each value is a SHA-256 string
or an object with ``sha256`` and optional ``bytes``. Paths are relative to the
index directory. Missing files and malformed indexes fail.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

digest_pattern = re.compile(r"[0-9a-f]{64}\Z")


def safe_path(name):
    if not isinstance(name, str) or not name or "\\" in name or "\n" in name or "\r" in name:
        raise ValueError("invalid evidence path")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in (".", "..") for part in path.parts):
        raise ValueError("evidence paths must stay beneath the index directory")
    return path


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def parse_index(data, path, field=None):
    if "SHA256SUMS" in path.name:
        if field:
            raise ValueError("--field applies only to JSON indexes")
        entries = {}
        for line in data.decode("utf-8").splitlines():
            if not line.strip():
                continue
            match = re.fullmatch(r"([0-9a-f]{64}) [ *](.+)", line)
            if not match or match.group(2) in entries:
                raise ValueError("malformed or duplicate SHA256SUMS entry")
            entries[match.group(2)] = match.group(1)
    else:
        obj = json.loads(data, object_pairs_hook=no_duplicates)
        if not isinstance(obj, dict):
            raise ValueError("JSON index must be an object")
        if field:
            entries = obj.get(field)
        elif isinstance(obj.get("evidence_sha256"), dict):
            entries = obj["evidence_sha256"]
        elif isinstance(obj.get("files"), dict):
            entries = obj["files"]
        else:
            entries = obj
    if not isinstance(entries, dict) or not entries:
        raise ValueError("index contains no evidence entries")
    normalized = {}
    for name, value in entries.items():
        safe_path(name)
        digest = value.get("sha256") if isinstance(value, dict) else value
        if not isinstance(digest, str) or not digest_pattern.fullmatch(digest):
            raise ValueError("index contains an invalid SHA-256")
        size = value.get("bytes") if isinstance(value, dict) else None
        if size is not None and (type(size) is not int or size < 0):
            raise ValueError("index contains an invalid byte count")
        normalized[name] = {"sha256": digest, "bytes": size}
    return normalized


class checkout_reader:
    def __init__(self, root):
        self.root = root.resolve()

    def read(self, path):
        file = self.root.joinpath(*path.parts)
        # A symlink makes the target and Git's stored bytes disagree. Fail
        # closed rather than following it, including intermediate symlinks.
        current = self.root
        for part in path.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("symlinks are not supported")
        return file.read_bytes()

    def close(self):
        pass


class git_reader:
    def __init__(self, root, revision):
        if not revision or revision.startswith("-") or "\n" in revision:
            raise ValueError("invalid Git revision")
        self.commit = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "--verify", revision + "^{commit}"],
            stderr=subprocess.DEVNULL, text=True).strip()
        tree = subprocess.check_output(["git", "-C", str(root), "ls-tree", "-rz", "--full-tree", self.commit])
        self.modes = {}
        for record in filter(None, tree.split(b"\0")):
            metadata, name = record.split(b"\t", 1)
            self.modes[os.fsdecode(name)] = metadata.split()[0]
        self.proc = subprocess.Popen(["git", "-C", str(root), "cat-file", "--batch"],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def read(self, path):
        mode = self.modes.get(str(path))
        if mode is None:
            raise FileNotFoundError(str(path))
        if mode not in (b"100644", b"100755"):
            raise ValueError("Git evidence entry is not a regular file")
        self.proc.stdin.write((self.commit + ":" + str(path) + "\n").encode())
        self.proc.stdin.flush()
        header = self.proc.stdout.readline().split()
        if len(header) == 2 and header[1] == b"missing":
            raise FileNotFoundError(str(path))
        if len(header) != 3 or header[1] != b"blob":
            raise ValueError("Git object is not a blob")
        size = int(header[2])
        data = self.proc.stdout.read(size)
        if len(data) != size or self.proc.stdout.read(1) != b"\n":
            raise ValueError("incomplete Git object")
        return data

    def close(self):
        self.proc.stdin.close()
        self.proc.stdout.close()
        if self.proc.wait() != 0:
            raise ValueError("Git object reader failed")


def verify(root, index, revision=None, field=None):
    index = safe_path(index)
    reader = git_reader(root, revision) if revision else checkout_reader(root)
    try:
        entries = parse_index(reader.read(index), index, field)
        failures = []
        for name, entry in entries.items():
            target = index.parent / safe_path(name)
            try:
                data = reader.read(target)
            except FileNotFoundError:
                failures.append({"path": name, "status": "MISSING"})
                continue
            actual = hashlib.sha256(data).hexdigest()
            if actual != entry["sha256"]:
                failures.append({"path": name, "status": "MISMATCH",
                                 "expected": entry["sha256"], "actual": actual})
            elif entry["bytes"] is not None and len(data) != entry["bytes"]:
                failures.append({"path": name, "status": "SIZE_MISMATCH",
                                 "expected": entry["bytes"], "actual": len(data)})
        return {"status": "PASS" if not failures else "FAIL", "index": str(index),
                "revision": reader.commit if revision else None, "checked": len(entries),
                "matched": len(entries) - len(failures), "failures": failures}
    finally:
        reader.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", help="repository-relative index path")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--revision", help="verify index and files from this Git commit")
    parser.add_argument("--field", help="JSON field containing the path-to-hash map")
    args = parser.parse_args()
    try:
        result = verify(args.root, args.index, args.revision, args.field)
    except (ValueError, OSError, UnicodeError, subprocess.SubprocessError) as exc:
        # Exception strings may contain the contributor's absolute checkout or
        # tool paths. Do not copy those into a report intended for sharing.
        print(json.dumps({"status": "ERROR", "error_type": type(exc).__name__}, indent=2))
        return 2
    print(json.dumps(result, indent=2))
    return int(result["status"] != "PASS")


if __name__ == "__main__":
    sys.exit(main())
