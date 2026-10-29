# PC / QEMU VirtIO-GPU 2D backend contract

Restricted QEMU 2D qualification passed; [frozen evidence](../reports/virtio_gpu_2d_qualified_20261029/qualification.json). This backend adds no syscall,
shared display struct, service operation or user mapping. Existing sys65/66 and
Display Service authenticated-channel policy remain unchanged. Qt sees the same
800×600 XRGB8888 mode and submits client RAM. The kernel copies authorized bytes
into its own backing pages, then commits a fenced 2D transfer/flush.

The driver is justified by a real device gap: VBE is a firmware framebuffer, while
VirtIO-GPU requires PCI discovery, negotiated virtqueues and owned DMA resources.
The generic user IPC/heap APIs cannot lawfully drive PCI or DMA, and user programs
are not granted raw BAR mapping, port IO or arbitrary physical memory. The platform
backend owns that hardware mechanism; file/window/application policy stays in
userspace. C20/C21/C22 boundaries and the existing identity model are preserved.

## Supported transport and ownership

PC PCI configuration mechanism #1, enumerated bus/slot/function, vendor/device
1af4:1050, type-0 memory BARs assigned by firmware. BAR size is probed with decode
and bus mastering temporarily disabled; command writes avoid W1C status fields.
Vendor capabilities, lengths, BAR bounds, notify multiplier and queue size are
checked. Only modern VERSION_1 is accepted; no packed ring, indirect/event-index,
3D, blob, VirGL or physical GPU support is advertised.

The kernel-only PCI UC aperture is separate from VBE's old 0x30000000 mapping.
`map_bar_range` maps bounded discovered capability subranges, not a hardcoded BAR
address or arbitrary userspace request. It is a small PC mapping allocator, not a
complete PCI resource manager, IOMMU or hotplug framework. Only below-4GiB assigned
MMIO BARs are supported. Single-core bootstrap/debug PCI access is serialized by
execution context; SMP/hotplug are NOT_RUN.

One split control queue of length 16, one outstanding request, explicit fences and
memory barriers. All descriptors point to allocated kernel pages. The 800×600
backing uses 469 scatter pages; queue + two command pages + response use four more.
The backing list crosses two command descriptors; physical contiguity is not
assumed. Used ID/length/index delta, response flags and fence identity are checked.
Completion polling is finite. Polling occurs only for commands, not while idle.

Resource 1 is the kernel's persistent display backing, not per-client memory or
an authority token. Client close reclaims the original process/surface resources;
the platform display remains alive. Resource 2 is used only in serial boot-monitor
qualification. Reset must acknowledge status zero before DMA pages can be freed.
If reset cannot be confirmed, pages stay quarantined; no reuse/UAF is claimed safe.
MMIO leaf mappings/page tables remain bounded kernel infrastructure, not per-client
resources. No reset/hotplug of a live multi-application session is promised.

## Failure, fallback and evidence

Initialize VBE independently, then prefer a successfully initialized GPU. If PCI,
features, queue, budget or resource initialization fails, VBE remains available.
With neither supported device, graphics fails explicitly and serial stays usable.
A runtime GPU present failure resets/quiesces owned DMA and fails closed through
existing unavailable errors; recovery after such failure is reboot, not transparent
live migration to VBE. Display Service/client death does not reset the device and
can recover through the existing new-service/new-client flow.

`gpu-test` is a kernel serial monitor diagnostic before `run`, not a user syscall.
It checks local bounds without submission, a genuine invalid-resource response,
three create/attach/scanout/detach/unref cycles and whole-device reset/reinit with
exact free-page accounting. Explicit build profiles set `--gpu-dma-page-limit 3`
and `--gpu-poll-limit 0`; these must fail initialization and retain VBE. Their
configuration enters both build identity and manifest, and they are not default
product settings.

Pixel evidence must come from a real GPU-only QEMU (`-vga none -device
virtio-gpu-pci`), with actual PCI/capability/request-completion traces. Compare the
same target Qt frame's RGB bytes across VBE and GPU and against the guest-exported
QImage; X is not a color channel. Dirty coordinates/offsets and boundaries must be
real. Present and QEMU-process CPU observations are reported separately; no speed
advantage is assumed. Negative user MMIO/PCI IO tests must fault and reclaim the
process. Source/SDK compatibility and resource counts bind each report.

Sources: [OASIS VirtIO 1.3 GPU](https://docs.oasis-open.org/virtio/virtio/v1.3/virtio-v1.3.html),
[QEMU device documentation](https://www.qemu.org/docs/master/system/devices/virtio/virtio-gpu.html).
The implementation is original Apache-2.0 code, with wire layouts derived from
the published specification; no external driver source was copied.

## C26 bootstrap/debug registration

Necessity: public user APIs intentionally cannot submit device commands or reset
hardware, while negative native responses, DMA accounting and reset/reinit need
real-device probes. Scope: `gpu-test` and `gpu-quota-test` in the trusted kernel
serial monitor before `run`; not a new user authority, syscall or service policy.
Owner: this VirtIO-GPU backend feature/maintainers (Codex implementation, recorded
in work log 0081). Exit condition: migrate advanced probes to an explicit test-only
profile when a separately designed device-management/quiescence interface can
exercise the same lifecycle safely. Until then they stay opt-in boot diagnostics,
never ordinary application startup. This registration grants no principle exception.
