# VirtIO-GPU 2D — final restricted QEMU evidence

[Qualification](qualification.json) · [scope/reproduction](../../work_log/0081_virtio_gpu_2d_qualification.md).

The final 21-suite matrix binds to upstream `85120a7` plus this backend, image
`c8bdc86d5bbc2629`. Positive GPU VMs use no VBE device. Same target Qt image matches
both scanouts, and all 1,440,000 RGB bytes match between backends; X is unused.
`gates/notes_interactive/` is the actual interactive Aurora Widgets editor on GPU,
with hardware-injected PS/2 input and byte-exact file saves/reboot readback.

Fault profiles distinguish real host resource quota, kernel DMA quota, forced zero
poll-budget timeout, VBE fallback and no-device rescue. Reset acknowledges before
DMA free; 473 pages are released/reallocated with exact accounting. User MMIO/PCI
IO probes fault. Related Qt, G02, thread, file and persistence regressions pass.

PNG/JSON stay directly readable. Raw serial, PPM and QImage data are losslessly
compressed as `.gz`. Sources, manifests, actual SDK/ELF hashes, runner-root adapter
hashes and configuration are retained. Compiled ELF/archive/image binaries remain
private, not a new Release. `exploratory/` is earlier probe/provenance data, never
rebinding old results. Complete 94f8e raw evidence remains in the private checkpoint.
Timing zero means below the 10ms guest clock; CPU is QEMU host-process time, not
stable guest utilization or proof of speed advantage. Absolute peak, hardware,
SMP, hotplug/live-device recovery, long stress, 3D/shaders/Quick and complete static
binary distribution/member/relink review are NOT_RUN.
