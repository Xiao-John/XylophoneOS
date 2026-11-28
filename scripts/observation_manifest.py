# SPDX-License-Identifier: Apache-2.0
"""Shared capability description; qualification belongs to a matching run."""


def observation_manifest_entry():
    return {'version': 1, 'syscall': 90, 'native_request_bytes': 48,
            'native_snapshot_bytes': 120,
            'scopes': ['self', 'direct_child', 'held_endpoint'],
            'deadline': 'absolute_monotonic_ns', 'read_only': True,
            'service': {'version': 1, 'request_bytes': 64, 'response_bytes': 208,
                        'max_clients': 4, 'max_reads_per_grant': 64,
                        'max_request_ns': 5000000000,
                        'authority': 'authenticated_peer_pid_and_image_generation',
                        'sources': ['process', 'service', 'resource', 'runtime', 'network', 'trust']},
            'proposal_execution': False, 'guest_qualification': 'separate_matching_run'}
