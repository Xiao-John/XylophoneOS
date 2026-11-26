#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify a Qt Quick materials directory and relink its external example."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import struct
import subprocess
import tempfile


link_flags = frozenset((
    "-static", "-no-pie", "-nostdlib", "-T", "-lm",
    "-Wl,--build-id=none,-z,noexecstack,-z,max-page-size=4096",
    "-Wl,--start-group", "-Wl,--end-group",
))
sysroot_name = "link/kit/runtime/sdk/sysroot"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def manifest_file(root, name):
    path = PurePosixPath(name)
    require(path.parts and not path.is_absolute() and path.as_posix() == name
            and ".." not in path.parts and "\\" not in name and "\n" not in name,
            "unsafe materials path: " + name)
    current = root
    for part in path.parts:
        current /= part
        require(not current.is_symlink(), "symbolic link in materials: " + name)
    require(current.is_file(), "missing materials file: " + name)
    return current


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def json_read(path):
    def unique(pairs):
        result = dict(pairs)
        require(len(result) == len(pairs), "duplicate key in " + path.name)
        return result

    return json.loads(path.read_bytes(), object_pairs_hook=unique)


def verified_manifest(root, expected=None):
    path = manifest_file(root, "manifest.json")
    digest = sha(path)
    require(expected is None or digest == expected, "materials manifest SHA-256 mismatch")
    manifest = json_read(path)
    require(manifest.get("format") == "xos_qt_quick_release_materials_v1", "unknown materials format")
    files = manifest.get("files")
    require(isinstance(files, dict) and files, "missing materials inventory")
    candidates = list(root.rglob("*"))
    require(not any(item.is_symlink() for item in candidates), "symbolic link in materials")
    require(all(item.is_file() or item.is_dir() for item in candidates), "special file in materials")
    actual = {item.relative_to(root).as_posix() for item in candidates if item.is_file()}
    require(actual == files.keys() | {"manifest.json"}, "materials file inventory differs")
    for name, entry in files.items():
        candidate = manifest_file(root, name)
        require(candidate.stat().st_size == entry["bytes"] and sha(candidate) == entry["sha256"],
                "materials content differs: " + name)
    return manifest, digest


def verify_static_elf(path):
    with path.open("rb") as stream:
        header = stream.read(64)
        require(len(header) == 64 and header[:7] == b"\x7fELF\x02\x01\x01"
                and struct.unpack_from("<HH", header, 16) == (2, 62), "expected x86-64 ET_EXEC")
        phdr = struct.Struct("<IIQQQQQQ")
        offset = struct.unpack_from("<Q", header, 32)[0]
        size, count = struct.unpack_from("<HH", header, 54)
        length = path.stat().st_size
        require(size == phdr.size and count > 0 and offset + size * count <= length,
                "invalid ELF program header table")
        stream.seek(offset)
        for _ in range(count):
            kind, flags, at, _, _, file_bytes, memory_bytes, _ = phdr.unpack(stream.read(phdr.size))
            require(kind not in (2, 3), "dynamic ELF is outside the static Quick profile")
            if kind == 1:
                require(flags & 3 != 3 and file_bytes <= memory_bytes and at + file_bytes <= length,
                        "invalid ELF LOAD mapping")


def build(root, output, expected, tool_prefix, replacements):
    manifest, material_digest = verified_manifest(root, expected)
    plan = json_read(manifest_file(root, "link/plan.json"))
    receipt = json_read(manifest_file(root, "link/application_receipt.json"))
    tools = {}
    for name in ("g++", "ld", "as"):
        resolved = shutil.which(tool_prefix + name)
        require(resolved is not None, "missing target tool: " + tool_prefix + name)
        tools[name] = Path(resolved).resolve(strict=True)
        require(sha(tools[name]) == receipt["target_tools"][name], "target tool differs: " + name)

    link_files = {entry["file"] for entry in plan if isinstance(entry, dict) and "file" in entry}
    overrides = {}
    for item in replacements:
        name, separator, path = item.partition("=")
        require(separator and name in link_files and name.startswith("link/kit/target/")
                and name.endswith(".a") and name not in overrides, "invalid Qt archive replacement: " + name)
        replacement = Path(path).resolve(strict=True)
        with replacement.open("rb") as stream:
            require(stream.read(8) == b"!<arch>\n", "replacement is not a complete static archive: " + name)
        overrides[name] = replacement

    arguments = []
    for entry in plan:
        if isinstance(entry, str):
            require(entry in link_flags, "unexpected link flag: " + entry)
            arguments.append(entry)
        else:
            require(isinstance(entry, dict) and entry.keys() == {"file"}, "invalid link input")
            name = entry["file"]
            require(name in manifest["files"], "unbound link input: " + name)
            arguments.append(str(overrides[name] if name in overrides else manifest_file(root, name)))

    require(not output.resolve().is_relative_to(root), "output must be outside the materials")
    output.mkdir(parents=True, exist_ok=False)
    replacement_digests = {name: sha(path) for name, path in overrides.items()}
    try:
        with tempfile.TemporaryDirectory(prefix="xos_relink_tools_") as directory:
            aliases = Path(directory)
            for name in ("as", "ld"):
                (aliases / name).symlink_to(tools[name])
            executable = output / "quick_app.elf"
            subprocess.run([str(tools["g++"]), "--sysroot=" + str(root / sysroot_name),
                            "-B" + str(aliases) + "/", *arguments, "-o", str(executable)], check=True)
        verify_static_elf(executable)
        require(all(sha(path) == receipt["target_tools"][name] for name, path in tools.items()),
                "target tool changed during relink")
        require(all(sha(path) == replacement_digests[name] for name, path in overrides.items()),
                "replacement archive changed during relink")
        verified_manifest(root, material_digest)
        digest = sha(executable)
        if not overrides:
            require(digest == receipt["elf_sha256"], "unmodified relink differs from the input ELF")
        report = {
            "status": "static_quick_application_linked",
            "elf": executable.name,
            "elf_sha256": digest,
            "kit_manifest_sha256": receipt["kit_manifest_sha256"],
            "materials_manifest_sha256": material_digest,
            "matches_reference": digest == receipt["elf_sha256"],
            "replacement_archives": replacement_digests,
        }
        (output / "receipt.json").write_text(json.dumps(report, indent=2) + "\n")
        return report
    except Exception:
        shutil.rmtree(output)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("verify", "relink"))
    parser.add_argument("--materials", type=Path, required=True)
    parser.add_argument("--expected-manifest-sha256")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--tool-prefix", default="x86_64-elf-")
    parser.add_argument("--replace", action="append", default=[], metavar="ARCHIVE=PATH")
    args = parser.parse_args()
    root = args.materials.resolve(strict=True)
    if args.operation == "verify":
        if args.output or args.replace:
            parser.error("--output and --replace require relink")
        manifest, digest = verified_manifest(root, args.expected_manifest_sha256)
        report = {"status": "verified", "manifest_sha256": digest, "files": len(manifest["files"])}
    else:
        if not args.output:
            parser.error("relink requires --output")
        report = build(root, args.output.resolve(), args.expected_manifest_sha256, args.tool_prefix, args.replace)
    print(json.dumps(report))


if __name__ == "__main__":
    main()
