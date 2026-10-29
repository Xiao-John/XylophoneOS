# SPDX-License-Identifier: Apache-2.0
"""Observe original imports and security failures; never provide compatibility shims."""
import importlib
import json
import os
import sys
import traceback

sys.path[:0] = ['/work/deps', '/work/localpilot']

def observe(name, function):
    try:
        value = function()
        row = {'name': name, 'status': 'PASSED', 'detail': repr(value)}
    except Exception as error:
        row = {'name': name, 'status': 'FAILED', 'exception': type(error).__name__,
               'error': str(error), 'traceback': traceback.format_exc()}
    print('DEPCHAIN:' + json.dumps(row), flush=True)

def original_import(name):
    module = importlib.import_module(name)
    return {'module': name, 'file': getattr(module, '__file__', None)}

def secure_create():
    path = '/work/modern2_private.json'
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(descriptor)
        # This is a negative probe on the current FAT profile. These values alone
        # cannot establish trusted ownership, even if a future adapter returns 0.
        return {'mode': oct(info.st_mode), 'uid': info.st_uid,
                'trusted_metadata_qualified': False}
    finally:
        os.close(descriptor)

for name in ['_posixsubprocess', 'fcntl', 'select', 'selectors', 'subprocess',
             '_socket', '_ssl', 'pypdf', 'pypdf.filters', 'PIL.Image',
             'localpilot_service', 'localpilot_service.protocol',
             'localpilot_service.security', 'localpilot_service.workspaces',
             'localpilot_service.cli', 'localpilot_api.service',
             'agent.permissions', 'agent.policy', 'agent.schemas']:
    observe(name, lambda name=name: original_import(name))
observe('private_create_nofollow', secure_create)
print('DEPCHAIN_DONE', flush=True)
