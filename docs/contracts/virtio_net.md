# VirtIO-Net N0/N1 hardware mechanism and user-service boundary

2026-10-29. Current implementation is linked only with explicit
`--net-boot-diagnostic`. The default kernel contains neither the NIC driver, its
console commands nor the exclusive diagnostic route state. Restricted **boot-diagnostic Ethernet** qualification; no installed
network service, IP/TCP/UDP/DNS, socket compatibility, HTTP or HTTPS qualification.
The network-device user ABI remains a separate proposed registration. No new
syscall number, shared SDK capability or application authority is allocated here.

## Reuse and actual gap

The existing `pci::find`, `memory_bar` and kernel-only `map_bar_range` are reused
unchanged. PCI mechanism #1 discovery, validated assigned BAR bounds and the UC
aperture are shared with VirtIO-GPU. GPU control packets, resource IDs, fenced
single synchronous queue, suppressed INTx and polling are GPU-specific and are
**not** treated as a network transport. This feature does not refactor or change
GPU's tested source. Net owns distinct asynchronous RX/TX queues and buffers.

Existing IPC cannot mint a device endpoint; heap/user mappings cannot authorize
BAR/DMA/PCI IO. The real ordinary-user isolation probe faults at vector14 for the
kernel PCI mapping and vector13 for `outl 0xcf8`, with exact process reclamation.
C28 requires a production user-mode driver to own device initialization, queues and
RX/TX; the kernel provides only registered authority and generic resource/IRQ
mechanisms. This opt-in hardware diagnostic does not implement that driver or
a user-device ABI. N2/lwIP/HTTP work is paused by the architecture-repair task. Kernel IPC and
scheduler do not interpret a networking business protocol. No program-name or
path-based authority, arbitrary user MMIO or user-provided DMA address is added.

## Supported device, buffers and queue semantics

Only QEMU modern PCI `1af4:1041`, type0 Ethernet class0200, valid capabilities and
firmware-assigned below4GiB memory BARs. Required features VERSION_1, MAC and
MRG_RXBUF; no checksum/GSO/TSO, event-index, indirect descriptors, packed rings,
control queue, MQ, hotplug, SMP, physical-device or IOMMU claim. MAC is read with a
bounded configuration-generation retry. MTU1500, Ethernet frame14–1514 bytes,
12-byte modern virtio header; VLAN/jumbo are rejected in this profile.

MRG_RXBUF is explicitly negotiated so the actual QEMU11.1.2 socket backend writes
`num_buffers`. Each RX buffer is4096 bytes, exceeding the maximum supported packet
1526 bytes, so every supported receive occupies one descriptor. A device completion
claiming multiple buffers fails the device closed. This is not merged-jumbo
reassembly. The first noMRG experiment exposed actual zero count headers and is
preserved as FAILED rather than weakening validation to accept zero.

Two length16 split rings; each has one page for descriptor/available/used sections
at0/256/512, and16 separate owned pages: **34 DMA pages** total. No physical
contiguity assumption. The memory allocator supplies zeroed kernel pages. Descriptor
ownership, index deltas, IDs (including duplicate IDs in a captured batch), writable
lengths and modern packet metadata are checked before copying. CPU/device memory
barriers precede publication/notification and follow observation.

TX copies a complete valid frame to an available owned slot and returns its length;
invalid size returns-22; queue full returns-11; unavailable/failed returns-19. No
partial enqueue is reported. RX completion copies into a bounded16-frame queue and
reposts the device buffer only after copy/rejection. Pending overflow drops whole
frames and increments a counter; it does not overwrite older unread frames.
Malformed short/over-MTU frames are rejected and counted. Invalid descriptor or
multi-buffer metadata fails closed rather than interpreting a continuation as a
new frame. These are private mechanism results, not a POSIX socket ABI.

## IRQ, idle and lifecycle

PIC initially masks all devices except PIT. Dedicated gates are installed for IRQ5,
9,10,11; firmware PCI interrupt line/pin are validated against that explicit subset.
The PC platform owns a single exclusive diagnostic route. It requires the selected
line to have been masked, changes only its ELCR/mask bits and necessary cascade
bit, then routes to the device-specific callback. Release restores only those
owned bits and preserves any other owner's mask/ELCR changes.
No assumption that IRQ11 is universal. Shared live-device IRQ multiplexing is not
qualified: the trusted pre-run diagnostic owns this previously masked route.

The ISR reads the device ISR status to acknowledge INTx, drains at most16 completions
per captured ring snapshot. The PC dispatcher issues the single normal
slave/master PIC EOI; the driver never acknowledges the PIC itself. It copies no
untrusted bytes outside bounded kernel storage and performs no protocol processing.
The existing arch `sti; hlt; cli` helper waits for real device/PIT interrupts with
the single core clock as its deadline source; there
is no idle network polling. The old boot monitor's UART polling is unchanged, so
this is not a claim about whole-system idle CPU.

Every diagnostic ends by releasing its platform-owned route and restoring only
its ELCR/PIC bits, then resetting
the device and waiting a finite number of status reads for acknowledgement before
returning DMA pages. A failed reset retains/quarantines pages and fails; no reuse
is claimed safe. Original PCI command bits are restored after a successful reset.
Successful reset reclaims all34 pages including still-posted RX/outstanding TX
ownership. A first mapping may retain one bounded infrastructure page table;
subsequent init/reset and quota failures do not accumulate pages. A failed probe
is not repeatedly remapped; retry requires reboot unless the complete transport
was already validated. Configuration/PCI mapping state survives successful reset.

## C20/C21/C22/C26 registration

Necessity: no existing legal user device mechanism can exercise network DMA and
IRQ/reset; those need real probes before requesting an ABI. Scope: opt-in trusted
`net-test`, `net-timeout`, `net-overflow`, `net-jumbo` in the serial boot monitor
before `run`; no automatic network init on ordinary boot, and no user authority.
Owner: this independent network foundation feature/maintainers, worklog0084.
Exit: move the consumer probes into a test-only service after the separately
registered device authority/copy/wait/lifecycle mechanism has merged and passed.
This C26 test-build registration is not a production networking service or
a delivered kernel driver. Default build exclusion is enforced, not merely a UI
label. Its eventual replacement requires the separately reviewed C28-compliant
user-mode driver/authority design; this repair does not implement or call it. It quiesces the NIC before ordinary userspace starts.

## Sources and evidence

Original Apache-2.0 implementation; no driver source copied. Wire semantics from
[OASIS VirtIO1.3 5.1](https://docs.oasis-open.org/virtio/virtio/v1.3/virtio-v1.3.html),
compared with [VirtIO1.2](https://docs.oasis-open.org/virtio/virtio/v1.2/virtio-v1.2.html).
QEMU source consulted at exact tag[v11.1.2](https://github.com/qemu/qemu/blob/v11.1.2/hw/net/virtio-net.c):
receive path lines1862–1870 and1904–1909 distinguish the noMRG extra-header assignment
from mergeable count copying. Actual guest header bytes are retained with the
failed experiment; source inference and measured behavior are distinguished.

Frozen qualification, raw serial/host packet bytes, hashes, fault profiles and
resource receipts: [network report](../reports/virtio_net_n1_20261029/qualification.json).

## Current clock/IRQ repair evidence

The original 9b832fa reports stay immutable. New ownership, boot initialization,
normal/diagnostic/probe profiles and affected regression evidence are indexed in
[the repair report](../reports/net_clock_irq_repair_20261029/README.md). The single
PIT counter is core/clock.cpp, written only through the actual IRQ0 path. PIC EOI
is pure I/O. RTC keeps its independent UTC snapshot/monotonic-anchor semantics.
