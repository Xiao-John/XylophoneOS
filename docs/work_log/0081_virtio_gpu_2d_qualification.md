# 0081 Optional VirtIO-GPU 2D backend — restricted real-guest qualification

2026-10-29. **PASSED (QEMU / single-core / 800×600 2D scope).** No 3D or Qt rendering
acceleration, new Release, full system qualification or physical-hardware claim.

A+B were delivered separately as PR #13 (`66ac002`), then merged by the maintainer
at upstream `94f8e30253c2789cd490f8806d1d3a16934534b1`; the accepted planning document
also arrived through `57c76a6`. This independent GPU worktree started at `c39cef1`,
kept a recoverable stash/checkpoint and all private builds, fast-forwarded to the
actual new main, resolved only the state-document insertion while preserving both
modules, then rebuilt and reran the full targeted matrix. Before delivery upstream
FB0 planning/tests advanced main to `85120a78efd4ae007571bf4c1415aedff2ad4e14` without
runtime/ABI changes; this final tree was fast-forwarded, rebuilt and independently
passed all 21 suites again. The complete `94f8e30` checkpoint remains private at
`build/virtio_gpu/checkpoint_94f8e_report`; its original qualification is retained
as exploratory provenance, not rebound to the new image. No direct push/merge to
upstream main, force push, unrelated cleanup or proxy/Clash/connection change.

## Implementation and architecture

- PC PCI configuration mechanism #1, actual enumeration and BAR size/capability
  validation. No guessed physical BAR address. Modern device 1af4:1050 negotiated
  VERSION_1; one length-16 split control queue with fenced requests/completions.
- Separate kernel-only PCI UC aperture with bounds/alignment and partial-map
  rollback, not reuse of the old VBE aperture as a supposed complete PCI framework.
  Users cannot access it or issue PCI IO; real probes fault with vectors 14/13.
- Allocated kernel-owned scatter backing: 469 frame pages plus four control pages.
  The attach-backing list crosses two command descriptors. No client pointer is
  given to the device; existing authenticated sys66 preflight/copy remains intact.
- Get display info; create/attach/scanout/transfer/flush; actual dirty coordinates
  and byte offsets. Used index/ID/length, reply length, flags and fence checked;
  memory barriers and bounded polling. No polling while idle.
- Device reset acknowledgement is required before freeing DMA. If it cannot be
  confirmed, ownership stays quarantined. Persistent resource 1 belongs to platform
  display lifetime, not to a user process. Three resource-2 cycles and whole reset/
  reinitialization reclaim exactly 473 pages and return to the same free-page count.
- VBE initialized independently and retained. No GPU or failed feature/queue/DMA/
  resource initialization falls back to VBE. No supported device leaves graphics
  unavailable and serial rescue usable. Runtime device failure fails closed;
  transparent live migration/hotplug/recovery is not promised.

No shared display ABI, syscall, service operation, Qt port, libc, terminal or xypm
implementation changed. Hardware mechanism belongs to the platform kernel backend;
identity, IPC and user-service lifecycle policy remain unchanged. New kernel/private
interfaces are not user ABI allocations. C20/C21/C22/C26 design/debug registration:
[contract](../contracts/virtio_gpu_2d.md).

## Frozen build, identity and compatibility

[Qualification and full SHA-256](../reports/virtio_gpu_2d_qualified_20261029/qualification.json).
Normal image: `build/virtio_gpu/latest_system/xos.img`, build `c8bdc86d5bbc2629`.
SHA-256 `c5cac2b2d96e367d9822517101f5525fed362b0b278065745dee8f086785c4be`.
Kernel ELF: `9b794259817ebb233fa7b5f1ee7677fc67f978dbf805bedda3746136a893e4f4`.
Default DMA budget 512 pages, completion poll budget 10,000,000 iterations.

Fault profiles are separate images/configurations and enter source/build identity:
DMA quota 3 pages: `b1958585a3221f94`; zero poll budget: `d38f1ba6596b9fde`.
They intentionally fail GPU initialization and demonstrate VBE fallback; they are
not the product defaults, or proof of a naturally wedged physical device deadline.

Every SDK artifact and runtime/shared source input was rehashed. Those inputs are
identical across the new upstream integration; the kernel-only build-recipe change
is recorded separately. Actual static Qt/Notes ELF and their receipt inputs were
reverified, not mixed with a guessed SDK. The same Qt 6.8.3 GUI ELF and Notes ELF
used on both backends retain their G05 source/SDK/Qt hashes; SDK recheck detail is
in `inputs/sdk_reverification.json`. Large compiled libraries/ELFs stay private;
only source, hashes and raw evidence are committed.

## Real guest matrix: 21 suites passed

QEMU 11.1.2 / pc-i440fx-10.0 / TCG / qemu64,+rdrand / one CPU / 512MiB. Positive GPU
runs use `-vga none -device virtio-gpu-pci`, so they cannot silently display through
VBE. PCI query/capability logs and actual native request-completion traces accompany
the scanout. No host writes to guest framebuffer or synthetic Qt event handlers.

- Paired VBE/GPU: same image/ELF, actual QPainter/font frame and clipped dirty corner
  updates. Both compare exactly with the guest-exported QImage, and with each other:
  **1,440,000 RGB bytes**, SHA-256
  `31af37eda326c732cf093ae7273e4e33edf9bf932f4952b955b62aeb9705dfee`.
  X is unused in XRGB8888/B8G8R8X8; this is color-byte equality, not a fabricated
  linear-MMIO read of GPU storage.
- Native invalid-resource/unknown-command/out-of-bounds responses are
  `0x1203 / 0x1200 / 0x1205`; local invalid rects submit nothing. Resource creation,
  attach, scanout, detach/unref cycles and whole reset/reinit pass; 39 requests and
  39 completions after the standard boot diagnostic, with exact page accounting.
- Host resource quota, host-init quota, kernel DMA quota, forced poll-budget timeout,
  and no-device rescue all pass. Host quota returns actual device `0x1201` while
  keeping the existing resource usable. Init failures release owned DMA and the
  same real Qt program still renders via VBE. No-device mode returns explicit -19.
- Actual Qt PS/2 key/mouse input, invalid operations via the existing gfxdemo check,
  repeat/focus/fault/second-window handling, Display Service death/restart, client
  cleanup and user MMIO/PCI IO isolation pass with exact baseline recovery.
- Aurora Notes on GPU: open/edit/multiline/selection/backspace/mouse/scroll, Ctrl+S,
  dirty Cancel/Discard, empty/BOM/CRLF/no-ending-newline/new-file saves, sync/reboot
  and six byte-exact file comparisons. Widgets process lifecycle passes separately.
- Related QtGui input/lifecycle and nine current-SDK QtCore suites pass: smoke,
  events/nested/timers, quota, fault, persistent readback, file errors, C++/TLS ABI,
  sampled memory and lifecycle. The adapter changes only runner ROOT/output paths;
  original/executed source hashes and real GPU QEMU commands are retained.
- Same integrated image: VBE G02 19 checks; thread core/pthread/C++ 15/10/10 checks;
  file/persistence 8/4 checks. No unsupported claim of full Dash/CPython/native GCC,
  hardware, SMP or long stress requalification. Documentation/ABI and 7-material
  license checks pass; member-level/relink/static-distribution review stays open.

Real screenshots: [VBE](../reports/virtio_gpu_2d_qualified_20261029/gates/paired/vbe-pixels.png),
[GPU](../reports/virtio_gpu_2d_qualified_20261029/gates/paired/virtio-pixels.png),
[Aurora Notes on GPU](../reports/virtio_gpu_2d_qualified_20261029/gates/notes_interactive/aurora-open.png),
[selection](../reports/virtio_gpu_2d_qualified_20261029/gates/notes_interactive/selection.png).
Serial, PPM and QImage bytes are retained losslessly as `.gz`.

## Performance and resource observations

Same ELF, three auto-scene intervals per backend; interval includes load/render/exit.
QEMU host-process CPU is accumulated CPU time / wall time, including emulator
threads and allowed to exceed 100%. It is not guest CPU percentage or a stable
benchmark. No speed advantage is established.

| Observation | VBE | VirtIO-GPU 2D |
|---|---:|---:|
| Maximum present sample | 10ms | 10ms |
| QEMU-process CPU samples | 102.53–108.35% | 104.99–107.92% |
| Auto-scene interval samples | 3.701–4.086s | 3.743–3.791s |
| Baseline free pages / tasks / completions | 130290 / 2 / 0 | 129817 / 2 / 0 |

The 473-page difference is 1,937,408 bytes of persistent GPU DMA/control backing;
MMIO page tables are bounded kernel infrastructure. Each client exit returns to
its own baseline. GPU Notes: 54 ordinary key samples, p95 10ms, maximum 20ms;
sampled user-page high water 7241 (28.29MiB). Clock granularity is 10ms; zero means
below that granularity. Absolute memory peak, long-run ring-wrap/stress, physical
hardware, SMP, other modes/multihead, live hotplug/device recovery, IOMMU containment,
3D/OpenGL/Vulkan/VirGL/shaders, QML/Quick and complete static distribution are NOT_RUN.

## Reproduce and next owner

```sh
python3 scripts/build.py --output-dir build/virtio_gpu/NEW_SYSTEM
python3 scripts/build.py --output-dir build/virtio_gpu/NEW_DMA --gpu-dma-page-limit 3
python3 scripts/build.py --output-dir build/virtio_gpu/NEW_TIMEOUT --gpu-poll-limit 0
QEMU="$QEMU_BIN" python3 tests/virtio_gpu_qualification.py \
  --system build/virtio_gpu/NEW_SYSTEM --quota-system build/virtio_gpu/NEW_DMA \
  --timeout-system build/virtio_gpu/NEW_TIMEOUT --qt-fixtures "$E17_BUILD_ROOT" \
  --qt-runner-root "$E17_SOURCE_ROOT" --output build/virtio_gpu/NEW_GATES
```

Build `access_fault.elf` from the supplied source using the hash-verified E17 SDK
`compile.py` into `build/virtio_gpu/` first. E17 build/consumer recipes are in 0078;
GPU itself builds independently without Qt. Output directories must be new. Early
-Werror indentation/conversion build failure was fixed, not suppressed; prior
successful probes remain explicitly exploratory/pre-integration evidence. Review
and merge the independent backend PR; do not retag an old Release or infer 3D/Quick
support from this 2D compatibility milestone.
