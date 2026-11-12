# SPDX-License-Identifier: Apache-2.0
"""Callable IPC v1 features and their separate guest qualification."""


def ipc_v1_manifest_entry():
    return {
        "abi_version": 1,
        "syscall": 88,
        "status": "supported",
        "features": [
            "endpoint_call_v1",
            "deadline_v1",
            "notification_v1",
            "wait_set_v1",
            "bulk_grant_v1",
        ],
        "guest_qualification": {
            "endpoint_call_v1": "previously_qualified",
            "deadline_v1": "previously_qualified",
            "notification_v1": "previously_qualified",
            "wait_set_v1": "previously_qualified",
            "bulk_grant_v1": "not_run",
        },
    }
