# 0104 Aurora Desktop G1 and G2-Scout

2026-10-30. **PASSED_SINGLE_SURFACE_PROTOTYPE**. This is an ordinary userland desktop
and bounded session policy, not a window manager or multiprocess compositor.

Wallpaper, status region, Dock/rail, launcher, Home/Studio/Settings/Quality, local
notices, panel hide/restore and keyboard controls run in real XOS. Session parent
requires the existing explicit child-spawn grant; child GUI apps receive none.
It authenticates child completion through existing wait, validates bounded app
requests against its fixed whitelist, releases the shell Surface, launches Notes,
Browser or independent Studio, waits and restores the shell. Preview mode is honest.
Notes' real unsaved guard is handled, not silently suppressed.

All three independent application handoffs, native controls/theme/accessibility,
legacy binary compatibility, exact normal/kill resources, display-death exit72,
serial rescue, service restart/new desktop and file sync pass. A real second GUI
process still receives EBUSY, ordinary direct-present is denied, and free connection
works after release. The actual failure probe uses existing v1 calls only; no
speculative syscall or compositor operation is allocated/called.

[Desktop evidence](../reports/aurora_glass_v2_20261030/desktop/README.md),
[build/use](../../src/ports/aurora_desktop/README.md) and
[transport gap](../contracts/aurora_compositor_proposal.md). Whole stack: 15 guest
suites/107 top-level checks, plus the SDK's 25 inner semantic assertions and host
blur vectors. All screenshots are real scanout. Kernel, shared ABI, libc, QPA and
time/IRQ/device source changes are zero, verified by the explicit scope audit.

Final aesthetic acceptance remains pending; the user chose Midnight Current as
the refinement direction. Live cross-process settings, a task switcher/window
manager, global file/dialog/notification brokers, modern WebView/Tauri, LocalPilot
runtime and GPU shaders/refraction are not delivered. Existing C28 driver debt and
PR20's CHANGES_REQUESTED blocker remain. No main push, merge or Release.

The next implementation is an independently reviewed generic IPC/lifecycle gate,
then a two-client copied CPU compositor. Do not bypass that gap through file-service
identity, private device access, app-name trust or an AI-specific kernel interface.

Frozen report: [qualification](../reports/aurora_glass_v2_20261030/qualification.json).
Base freshly fetched/rechecked upstream `3377dbf35bdb43d850c9a2b8e8076da3be146f3d`.
Current system build `7ccd5871c0c00297`, image SHA256
`165686bb0de0b0b2f33645ede2cf10c2badb25ea363f3ef57ed74641503b0b08`.
QtBase 6.8.3; one core/512MiB/800×600/QEMU11.1.2 TCG. The matching frozen E17
threading SDK and Qt Core/Gui/Widgets archives are rehashed before target builds.
17 existing shared/SDK headers were compared: 16 exact, one additive unused
execution receipt helper; no system ABI/layout/opcode changes are made here.
All target build commands, tool/archive/SDK/ELF/image hashes, screenshots and raw
logs are frozen. Tests use only dedicated synthetic FAT disks. No Release.
