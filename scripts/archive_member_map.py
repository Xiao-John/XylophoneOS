#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Read GNU archives and verify build-produced member provenance manifests."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath

repo_root = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--root", type=Path, default=repo_root)
    parser.add_argument("--build-id", required=True)
    args = parser.parse_args()
    try:
        result = verify_manifest(args.manifest, args.root, args.build_id)
    except (OSError, ValueError) as error:
        parser.exit(1, f"archive manifest: {error}\n")
    print(json.dumps(result, sort_keys=True))


def read_archive(path):
    """Return members in archive order; reject ambiguous name-only mappings."""
    data = Path(path).read_bytes()
    if data[:8] != b"!<arch>\n":
        raise ValueError(f"not a plain GNU ar archive: {path}")
    offset, longnames, members = 8, b"", {}
    while offset < len(data):
        header = data[offset:offset + 60]
        if len(header) != 60 or header[58:] != b"`\n":
            raise ValueError(f"invalid archive header at {offset}: {path}")
        token = header[:16].decode("ascii").strip()
        size_text = header[48:58].strip()
        if not size_text.isdigit():
            raise ValueError(f"invalid archive member size at {offset}: {path}")
        size = int(size_text)
        body, end = offset + 60, offset + 60 + size
        if end + size % 2 > len(data):
            raise ValueError(f"truncated archive member at {offset}: {path}")
        if size % 2 and data[end:end + 1] != b"\n":
            raise ValueError(f"invalid archive padding at {end}: {path}")
        payload = data[body:end]
        offset = end + size % 2
        if token == "//":
            longnames = payload
            continue
        if token in ("/", "/SYM64/"):
            continue
        if token.startswith("/") and token[1:].isdigit():
            start = int(token[1:])
            end_name = longnames.find(b"/\n", start)
            if (end_name < 0 or (start != 0 and longnames[start - 2:start] != b"/\n")):
                raise ValueError(f"invalid GNU long-name reference {token}: {path}")
            name = longnames[start:end_name].decode("utf-8")
        elif token.endswith("/") and not token.startswith("/"):
            name = token[:-1]
        else:
            raise ValueError(f"unsupported GNU archive member name {token!r}: {path}")
        if not name:
            raise ValueError(f"empty archive member name: {path}")
        if name in members:
            raise ValueError(f"duplicate archive member {name!r}; name-only provenance is ambiguous")
        members[name] = payload
    return members


def verify_manifest(manifest_path, root, build_id):
    """Check content identity; build-time capture remains the producer's duty."""
    manifest = json.loads(Path(manifest_path).read_text())
    if not isinstance(manifest, dict) or manifest.get("version") != 1:
        raise ValueError("expected a version 1 manifest object")
    if not build_id or manifest.get("build_id") != build_id:
        raise ValueError("build_id mismatch")
    archive = repository_path(root, manifest.get("archive"), "archive")
    repository_path(root, manifest.get("generator"), "generator")
    if 'generator_sha256' in manifest:
        check_digest(repository_path(root, manifest['generator'], 'generator'), manifest['generator_sha256'])
    if 'imported_manifest' in manifest:
        check_digest(repository_path(root, manifest['imported_manifest'], 'imported manifest'), manifest.get('imported_manifest_sha256'))
    check_digest(archive, manifest.get("archive_sha256"))
    actual = read_archive(archive)
    records = manifest.get("members")
    if not isinstance(records, list):
        raise ValueError("members must be an array")
    listed, derived = set(), 0
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("member record must be an object")
        member = record.get("member")
        if not isinstance(member, str) or not member:
            raise ValueError("member name must be a non-empty string")
        if member in listed:
            raise ValueError(f"duplicate manifest member {member!r}")
        listed.add(member)
        if 'object_sha256' in record and hashlib.sha256(actual.get(member, b'')).hexdigest() != record['object_sha256']:
            raise ValueError(f'object digest mismatch: {member}')
        source = repository_path(root, record.get("source"), "source")
        check_digest(source, record.get("source_sha256"))
        category = record.get("declaration_class")
        if not isinstance(category, str) or not category:
            raise ValueError(f"missing declaration_class for {member}")
        inferred = record.get("derived", False)
        if not isinstance(inferred, bool):
            raise ValueError(f"derived must be boolean for {member}")
        derived += inferred
    if listed != set(actual):
        raise ValueError(f"member set mismatch: missing={sorted(set(actual) - listed)}, "
                         f"extra={sorted(listed - set(actual))}")
    return {"archive": manifest["archive"], "build_id": build_id,
            "members": len(actual), "derived_members": derived,
            "content_verified": True}


def verify_bundle(root, provenance, allowed_legacy=()):
    if not isinstance(provenance, dict) or provenance.get('version') != 1:
        raise ValueError('SDK requires version 1 archive_provenance')
    manifests, legacy = provenance.get('manifests'), provenance.get('legacy_archives')
    if not isinstance(manifests, dict) or not isinstance(legacy, dict):
        raise ValueError('archive manifests and legacy archives must be mappings')
    if not set(legacy) <= set(allowed_legacy):
        raise ValueError('unregistered legacy archive exemption')
    represented, results = set(), []
    for relative, expected in manifests.items():
        path = repository_path(root, relative, 'manifest')
        check_digest(path, expected)
        entry = json.loads(path.read_text())
        result = verify_manifest(path, root, entry.get('build_id'))
        if result['derived_members'] or entry.get('capture') != 'compiler-invocation-and-object-bytes':
            raise ValueError('new archive requires captured compiler/object provenance')
        if result['archive'] in represented:
            raise ValueError('duplicate archive provenance')
        represented.add(result['archive'])
        results.append(result)
    for relative, expected in legacy.items():
        if relative in represented:
            raise ValueError('archive is both captured and legacy')
        check_digest(repository_path(root, relative, 'legacy archive'), expected)
        represented.add(relative)
    actual = {path.relative_to(root).as_posix() for path in Path(root).rglob('*.a')}
    if actual != represented:
        raise ValueError(f'archive coverage mismatch: missing={sorted(actual - represented)}, extra={sorted(represented - actual)}')
    return {'captured': results, 'legacy_archives': sorted(legacy), 'all_archives_accounted': True}


def repository_path(root, value, field):
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"{field} must be a repository-relative POSIX path")
    path = PurePosixPath(value)
    if not path.parts or path.is_absolute() or ".." in path.parts or ":" in path.parts[0]:
        raise ValueError(f"{field} must be a repository-relative POSIX path")
    return Path(root) / value


def check_digest(path, expected):
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(f"sha256 mismatch: {path}")


if __name__ == "__main__":
    main()
