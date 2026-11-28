# PCI reset observer lifetime

The generic device-grant backend may retain one read-only VirtIO reset-status
observer while a grant owns a device. It uses this observer to verify reset
completion before releasing DMA backing pages. The observer is kernel-private;
it is not a hotplug identity, a live presence query or a user-granted MMIO right.

A PCI BDF can identify different functions over time. Disabling a grant must
therefore unmap its observer after the final DMA-stop observation and retire
the slot. A later grant performs current PCI inspection and maps the newly
reported BAR. It cannot accept the old observer merely because the BDF matches.

Sixteen pages at the end of the existing kernel PCI aperture are reserved for
these bounded, reusable observer slots. The existing display/boot mapper stops
before that reserved range. Normal stop, close and revoke use the same backend
disable path. If unmap fails, the slot remains occupied and subsequent grant
inspection fails closed. A failed new mapping publishes no observer. Existing
DMA quarantine rules and public syscall layouts are unchanged.

`tests/pci_observer_host.py` compiles the production PCI implementation with
only PIO and page-table boundaries replaced. It checks same-BDF replacement
with a different BAR, independent new reset status, retirement, mapping failure,
unmap failure and missing BAR rejection. The separate P1-I2 actual guest report
qualifies service stop/wait, actual host-controlled PCI disappearance and
reappearance, fresh grants, DHCP/ACD and exact resource recovery. It explicitly
does not qualify unannounced automatic hotplug, firmware resource allocation,
ACPI eject acknowledgment or a physical NIC.
