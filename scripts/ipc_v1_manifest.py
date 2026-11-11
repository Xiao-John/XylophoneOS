# SPDX-License-Identifier: Apache-2.0
"""Shared SDK manifest entry for IPC v1 before a runtime backend is qualified."""


def ipc_v1_manifest_entry():
    return {
        "abi_version": 1,
        "syscall": 88,
        "status": "registered_unsupported",
        "features": [],
    }
