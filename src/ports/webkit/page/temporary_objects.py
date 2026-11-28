# SPDX-License-Identifier: Apache-2.0
"""Keep only reproducible CMake target objects in one live SDK's private tmpfs."""
from hashlib import file_digest
import json
import os
from pathlib import Path
import shlex
import shutil


def digest(path):
    with path.open('rb') as stream: return file_digest(stream, 'sha256').hexdigest()


def target_directories(cmake):
    result = set()
    for entry in json.loads((cmake / 'compile_commands.json').read_bytes()):
        arguments = entry.get('arguments') or shlex.split(entry['command'])
        if '-o' not in arguments: continue
        obj = Path(arguments[arguments.index('-o') + 1])
        if not obj.is_absolute(): obj = Path(entry['directory']) / obj
        obj = Path(os.path.normpath(obj))
        # Do not resolve a previously redirected directory during --resume.
        relative = obj.relative_to(cmake)
        for index, part in enumerate(relative.parts[:-1]):
            if part == 'CMakeFiles' and relative.parts[index + 1].endswith('.dir'):
                result.add(Path(*relative.parts[:index + 2])); break
        else: raise ValueError('compile object has no CMake target directory: ' + str(obj))
    if not result: raise ValueError('CMake did not expose any target object directories')
    return sorted(result)


def redirect(cmake, temporary, record_path, resume):
    """Redirect target directories while preserving persistent generated headers."""
    if not temporary.is_absolute() or not temporary.is_relative_to('/tmp') or temporary == Path('/tmp'):
        raise ValueError('temporary objects require a dedicated SDK /tmp child directory')
    if temporary != temporary.resolve(): raise ValueError('temporary object root must be canonical and not a symlink')
    previous = None
    if record_path.exists():
        previous = json.loads(record_path.read_bytes())
        if (not resume or previous['temporary_directory'] != str(temporary)
                or previous['phase'] != 'active' or not temporary.is_dir()):
            raise ValueError('temporary objects are not resumable in this SDK session')
    elif temporary.exists():
        raise ValueError('select a fresh temporary object directory')
    temporary.mkdir(parents=True, exist_ok=resume)
    directories = set(target_directories(cmake))
    if previous:
        for name in previous['directories']:
            relative = Path(name)
            if relative.is_absolute() or '..' in relative.parts or relative.as_posix() != name:
                raise ValueError('noncanonical previous target directory')
            directories.add(relative)
    directories = sorted(directories)
    for relative in directories:
        source, target = cmake / relative, temporary / relative
        if source.is_symlink():
            if source.resolve(strict=True) != target or not resume:
                raise ValueError('unexpected target directory link: ' + str(source))
            continue
        if target.exists(): raise ValueError('temporary target already exists: ' + str(target))
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.exists(): shutil.move(source, target)
        else: target.mkdir()
        source.symlink_to(target, target_is_directory=True)
    record = {'version': 1, 'phase': 'active', 'temporary_directory': str(temporary),
              'directories': [str(path) for path in directories]}
    record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
    return record


def release(cmake, temporary, record_path):
    """Record disposable objects and retain every other generated file before unlinking."""
    record = json.loads(record_path.read_bytes())
    if record['phase'] != 'active' or record['temporary_directory'] != str(temporary):
        raise ValueError('temporary object lifecycle is not active')
    files, object_bytes = {}, 0
    for relative in map(Path, record['directories']):
        if relative.is_absolute() or '..' in relative.parts or relative.as_posix() != str(relative):
            raise ValueError('noncanonical temporary target directory')
        source, target = cmake / relative, temporary / relative
        if not source.is_symlink() or source.resolve(strict=True) != target:
            raise ValueError('temporary target link changed: ' + str(source))
        replacement = source.with_name(source.name + '.persistent')
        if replacement.exists(): raise ValueError('unfinished object export: ' + str(replacement))
        replacement.mkdir()
        for path in sorted(target.rglob('*')):
            name = path.relative_to(target)
            if path.is_symlink():
                # Generated build links may encode an unavailable private temp path.
                raise ValueError('unexpected symlink inside target objects: ' + str(path))
            if path.is_dir(): (replacement / name).mkdir(parents=True, exist_ok=True); continue
            if not path.is_file(): raise ValueError('unsupported generated object entry: ' + str(path))
            if path.suffix in ('.o', '.obj'):
                files[(relative / name).as_posix()] = {'sha256': digest(path), 'size': path.stat().st_size}
                object_bytes += path.stat().st_size
            else:
                destination = replacement / name; destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, destination)
                if digest(destination) != digest(path): raise ValueError('generated file export mismatch')
        source.unlink(); os.replace(replacement, source)
        shutil.rmtree(target)
    shutil.rmtree(temporary)
    record.update(phase='released_after_regular_archive_link', objects=files, object_bytes=object_bytes,
                  object_count=len(files), incremental_rebuild_requires_recompilation=True)
    record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
    return record
