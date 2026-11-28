# SPDX-License-Identifier: Apache-2.0
"""Verify a separately frozen native producer without relabeling the app SDK."""
from hashlib import file_digest
from pathlib import Path


def native_inputs(system, source_root):
    prefixes = ('src/boot/', 'src/kernel/', 'src/shared/', 'src/user/')
    application_headers = (
        'src/ports/webkit/browser/installation.hpp',
        'src/ports/webkit/browser/protocol.hpp',
        'src/ports/webkit/browser/transport.hpp',
    )
    checked = {}
    for name, expected in system['sources'].items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('native manifest contains an invalid source path')
        if not name.startswith(prefixes) and name not in application_headers:
            continue
        with (source_root / relative).open('rb') as stream:
            actual = file_digest(stream, 'sha256').hexdigest()
        if actual != expected:
            raise ValueError('qualified native source changed: ' + name)
        checked[name] = actual
    required = (
        'src/kernel/platform/pc/pci.cpp', 'src/kernel/arch/x86_64/paging.cpp',
        'src/user/programs/clarke_session.hpp', 'src/user/loader/load.cpp',
        'src/user/network/service_core.cpp', 'src/user/interactium/service.cpp',
        'src/user/interactium/dispatcher.cpp', 'src/user/interactium/window_manager.cpp',
        *application_headers,
    )
    if not set(required) <= checked.keys():
        raise ValueError('native manifest omits a required browser implementation input')
    return checked
