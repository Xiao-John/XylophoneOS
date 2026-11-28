# SPDX-License-Identifier: Apache-2.0
"""Describe the ordinary copied multiwindow protocol independently of libc."""


def interactium_manifest_entry():
    return {'wire_version': 1, 'header_bytes': 48, 'message_bytes_max': 4096,
            'service_name': 'interactium', 'transport_syscalls': [84, 85, 86],
            'client_header': 'xos/interactium_client.hpp',
            'authority': 'authenticated_endpoint_peer_pid_and_session',
            'sessions_max': 4, 'windows_per_session_max': 8, 'drawable_surfaces_global_max': 8,
            'surface_width_max': 800, 'surface_height_max': 600,
            'pixel_format': 'ARGB8888_premultiplied', 'transport': 'bounded_copied_tiles',
            'deadline': 'caller_absolute_monotonic_ns', 'automatic_replay': False,
            'frame_commit': 'private_staging_to_front', 'damage': 'derived_from_accepted_tiles',
            'display_backend': 'exclusive_display_v1', 'guest_qualification': 'separate_matching_run'}
