#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Collect and constrain real compiler dependencies for G1 diagnostic objects."""
import hashlib
from pathlib import Path
import shlex


def collect_dependency_files(depfile, source_dir, build_dir, compiler_include, expected_name=None):
    source_dir = Path(source_dir).resolve(strict=True)
    build_dir = Path(build_dir).resolve(strict=True)
    compiler_include = Path(compiler_include).resolve(strict=True)
    roots = [('source', source_dir), ('build', build_dir),
             ('compiler', compiler_include), ('compiler-fixed', compiler_include.parent / 'include-fixed')]
    rule = Path(depfile).read_text().replace('\\\n', ' ').splitlines()[0]
    if ':' not in rule:
        raise ValueError('missing dependency rule')
    target, dependencies = rule.split(':', 1)
    target = target.replace('$(common-objpfx)', str(build_dir) + '/')
    object_file = Path(target).resolve(strict=True)
    relative_object = object_file.relative_to(build_dir)
    if (len(relative_object.parts) != 2 or relative_object.suffix != '.o'
            or (expected_name is not None and relative_object.name != expected_name + '.o')):
        raise ValueError('unexpected object path')
    workdir = source_dir / relative_object.parts[0]
    dependencies = dependencies.replace('$(common-objpfx)', str(build_dir) + '/')
    dependencies = dependencies.replace('$(..)', str(source_dir) + '/')
    found = {}
    for name in shlex.split(dependencies):
        if '$' in name:
            raise ValueError('unexpanded dependency variable')
        path = (workdir / name).resolve(strict=True)
        for label, root in roots:
            if path == root or root in path.parents:
                key = label + '/' + path.relative_to(root).as_posix()
                found[key] = hashlib.sha256(path.read_bytes()).hexdigest()
                break
        else:
            raise ValueError('unexpected dependency: ' + str(path))
    if not found:
        raise ValueError('empty dependency list')
    return found
