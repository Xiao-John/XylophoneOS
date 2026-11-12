# SPDX-License-Identifier: Apache-2.0
"""Available device mechanisms; hardware qualification is recorded separately."""


def device_manifest_entry():
    return {
        "abi_version": 1,
        "syscall": 112,
        "status": "implemented_unverified",
        "operations": ["grant", "query", "map", "unmap", "dma_alloc", "dma_release",
                       "irq_bind", "irq_wait", "irq_ack", "revoke", "close"],
        "profile": "exclusive_unused_pci_network_function",
        "authority": "bootstrap_supervisor_owned_building_child",
        "dma_isolation": "trusted_driver_and_device_no_iommu",
        "dma_devices": ["virtio_net_pci_1af4_1041", "virtio_net_modern_capabilities_1af4_1000"],
        "dma_release": "kernel_observed_virtio_reset_or_quarantine",
        "guest_qualification": "not_run",
    }
