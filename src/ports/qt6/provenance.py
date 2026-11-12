# SPDX-License-Identifier: Apache-2.0
"""Use CMake's compiler launcher and archive finish hooks for member capture."""
import hashlib
import json
from pathlib import Path
import shlex
import sys


def cmake_capture_options(arguments, command):
    root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(root / 'scripts'))
    from archive_provenance import capture_build
    recipe = {'configure': command,
              'sdk': hashlib.sha256((arguments.sdk / 'manifest.json').read_bytes()).hexdigest(),
              'generator': hashlib.sha256((root / 'scripts/archive_provenance.py').read_bytes()).hexdigest()}
    build_id = hashlib.sha256(json.dumps(recipe, sort_keys=True).encode()).hexdigest()
    capture = capture_build(arguments.build, build_id, 'qt-mixed-source-declarations')
    launcher = ';'.join(capture.launcher())
    archive = capture.launcher()
    archive[2] = 'archive'
    finish = '<CMAKE_RANLIB> <TARGET>;' + shlex.join(archive) + ' <TARGET>'
    (arguments.build / 'provenance_config.json').write_text(json.dumps(
        {'build_id': build_id, 'recipe': recipe, 'guest_qualification': 'not_run'},
        indent=2, sort_keys=True) + '\n')
    return ['-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
            *['-DCMAKE_' + language + '_COMPILER_LAUNCHER=' + launcher for language in ('C', 'CXX', 'ASM')],
            *['-DCMAKE_' + language + '_ARCHIVE_FINISH=' + finish for language in ('C', 'CXX')]]
