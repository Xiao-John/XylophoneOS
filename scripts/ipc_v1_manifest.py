# SPDX-License-Identifier: Apache-2.0
"""Shared SDK manifest entry for guest-qualified IPC v1 feature groups."""


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
        ],
    }
