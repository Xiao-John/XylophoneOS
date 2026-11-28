# SPDX-License-Identifier: Apache-2.0
"""Describe the opt-in Net2 socket profile without implying guest qualification."""


def net_readiness_manifest_entry():
    return {
        'wire_version': 2,
        'capabilities': {'operation': 15, 'legacy_flags': 0, 'legacy_revision': 1,
                         'extended_flags': 1, 'extended_revision': 2, 'extended_mask': 15},
        'readiness_bind': {'operation': 19, 'reply_bytes': 32, 'grant_bytes': 4096,
                           'page_revision': 1, 'page_bytes': 128, 'max_records': 2,
                           'server_rights': 11, 'client_rights': 1, 'transport': 'sys88_bulk_grant'},
        'kernel_features': {'query_flags': 2, 'required_mask': 48, 'holder_release_action': 24},
        'shutdown_read': {'operation': 20, 'page_event': 64},
        'immediate_negative': 'sampled_during_current_call_or_eagain',
        'posix_cancellation': 'unsupported',
        'guest_qualification': 'not_run',
    }
