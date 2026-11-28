# SPDX-License-Identifier: Apache-2.0
"""Verify rebuilt WebCore prerequisites without inheriting old qualifications."""
from hashlib import file_digest, sha256
import json
from pathlib import Path, PurePosixPath


def digest(path):
    with Path(path).open('rb') as stream:
        return file_digest(stream, 'sha256').hexdigest()


def target_inputs(target, status, sdk_tree, *, artifact_root=None, headers='prefix/include'):
    target = Path(target)
    manifest = target / 'manifest.json'
    data = manifest.read_bytes()
    record = json.loads(data)
    if record.get('status') != status:
        raise ValueError('incomplete target dependency: ' + target.name)
    binding = record.get('profile_binding', {})
    if record.get('sdk_tree_sha256', binding.get('sdk_tree_sha256')) != sdk_tree:
        raise ValueError('dependency belongs to another SDK: ' + target.name)
    artifacts = record.get('artifacts')
    if not isinstance(artifacts, dict) or not artifacts:
        raise ValueError('dependency has no artifact receipt: ' + target.name)
    artifact_root = Path(artifact_root) if artifact_root is not None else target
    header_root = artifact_root / headers
    inputs = {manifest: sha256(data).hexdigest()}
    for name, expected in artifacts.items():
        relative = PurePosixPath(name)
        if (relative.is_absolute() or relative.as_posix() != name
                or any(part in ('.', '..') for part in relative.parts)):
            raise ValueError('noncanonical dependency artifact: ' + name)
        path = artifact_root
        for part in relative.parts:
            path = path / part
            if path.is_symlink():
                # ICU's versioned metadata selectors are allowed only when the
                # same target file is independently recorded inside this prefix.
                resolved = path.resolve(strict=True)
                if (path != artifact_root / relative or path.is_relative_to(header_root)
                        or not resolved.is_relative_to(artifact_root.resolve())
                        or artifacts.get(resolved.relative_to(artifact_root.resolve()).as_posix()) != expected):
                    raise ValueError('symlink dependency artifact: ' + name)
        if not path.is_file() or digest(path) != expected:
            raise ValueError('dependency artifact differs: ' + name)
        inputs[path] = expected
    header_files = {path for path in header_root.rglob('*') if path.is_file()}
    if not header_files or not header_files <= inputs.keys():
        raise ValueError('dependency headers are not completely bound: ' + target.name)
    return record, inputs


def recheck_inputs(inputs):
    for path, expected in inputs.items():
        if digest(path) != expected:
            raise ValueError('dependency changed during build: ' + str(path))
