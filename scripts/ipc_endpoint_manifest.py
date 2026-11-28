# SPDX-License-Identifier: Apache-2.0
"""Describe sys84--86 limits from the shared kernel/SDK ABI header."""
from pathlib import Path
import re


def ipc_endpoint_manifest_entry():
    header = Path(__file__).resolve().parents[1] / 'src/shared/include/xos/process_abi.hpp'
    values = dict(re.findall(r'\b(ipc_max_owned_channels|ipc_max_owned_names)\s*=\s*(\d+)',
                             header.read_text()))
    if set(values) != {'ipc_max_owned_channels', 'ipc_max_owned_names'}:
        raise ValueError('generic IPC limits are absent from the shared ABI header')
    return {'syscalls': [84, 85, 86], 'quota_owner': 'authenticated_pid',
            'max_owned_channels': int(values['ipc_max_owned_channels']),
            'max_owned_names': int(values['ipc_max_owned_names']),
            'pending_connections_count_as_channels': True, 'guest_qualification': 'not_run'}
