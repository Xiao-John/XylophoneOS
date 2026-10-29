# Existing-interface gap: real guest rejection probe

2026-10-29. **PASSED (the required rejection), not a new device API pass.**
The independent N1 candidate `codex/browser-net-n1` built system `67883ca24e9dcdae`.
Two real VirtIO-Net cycles first exchanged32 exact Ethernet frames with an isolated
host socket peer; the driver then reset and reclaimed its DMA before `run`.
Kernel-only BAR mappings remain in kernel address space. This is actual Ethernet,
not guest TCP or a proposed syscall implementation.

The existing ordinary SDK fixture `tests/fixtures/virtio_gpu/access_fault.cpp` was
freshly linked with the verified E17 SDK. The ordinary process attempted a store at
kernel-only PCI virtual address `0x32000000`: page fault vector14. A second process
attempted PCI configuration `OUT` to `0xcf8`: general-protection vector13. After each
fault, free pages/tasks/completions returned exactly to `[130280,2,0]`; Xshell/file
service and serial rescue remained alive. `guest-report.json` and lossless
`guest-serial.log.gz` preserve the command, PCI inventory, raw counters and faults.
`inputs.json` binds the candidate runtime and test inputs; this design branch does
not contain or pretend to implement the N1 candidate itself.

The first optional-isolation runner attempted an unsupported128MiB FAT32 fixture
and failed before QEMU; it was corrected to512MiB. Its next run observed the actual
page fault but expected trace-format wait output with tracing disabled; explicit
trace setup fixed the harness. Those failed attempts remain in the N1 private
build/frozen network report. The successful receipt is from the final corrected
runner and final image, not a relabelled earlier run.

Together with source inspection of authenticated fixed IPC endpoints and
spawn-only `sys_process_grant`28, this demonstrates the actual access gap. Exposing
raw PCI/DMA would defeat the tested isolation; the proposed narrow versioned device
right/ownership/wait mechanism is in [the claim design](../../contracts/network_device_v1_proposal.md).
The claimed112 entry still has no source constant, dispatch or SDK supported bit.
