# Aurora Glass v2 / G1 / SSG — scoped guest delivery

2026-10-30 · base `3377dbf` · system build `7ccd5871c0c00297`.
**15 scoped guest suites / 107 top-level checks passed**, plus 25 native semantic
assertions and 396 exact blur vectors + 6 rejection controls under host sanitizers.
The render gate is the final enhanced 11-run probe, not the superseded intermediate.

- [SDK/quality/local Intent](sdk/README.md)
- [Notes/Browser SSG and affected regressions](ssg/README.md)
- [Single-Surface desktop/session](desktop/README.md)
- [Artifact/source hashes and scope](qualification.json)
- [Frozen evidence hashes](evidence_index.json)
- [Original failed attempts](failures/README.md)

Every screenshot is real QEMU scanout; PNGs are lossless derivatives and original
PPMs/logs are retained compressed. The actual image SHA-256 is
`165686bb0de0b0b2f33645ede2cf10c2badb25ea363f3ef57ed74641503b0b08`.
SDK/Qt archives, target ELFs, build commands and source hashes are bound in inputs/.
No target ELF, Qt archive, model or private LocalPilot source is published here.
The optional render SDK program was rebuilt after the OS image without changing
kernel/QPA/system ABI, then independently loaded and requalified on that same image.
This is ordinary C16 independent application development, not a new system build claim.

Kernel source/system ABI changes: **0**. No private clock, IRQ, MMIO or DMA mechanism.
C04's AI-native direction records the user's explicit instruction; AI remains userland.
Global live theme negotiation, a multiprocess compositor/SSG broker, production action
authority, modern WebView/Tauri, LocalPilot runtime and GPU shaders remain unavailable.
The user selected Midnight Current for refinement; final aesthetic acceptance is pending.
Physical hardware/SMP/long stress, true allocator OOM and static product distribution
are not qualified. Historical whole-system/Qt results are not rebound to this report.
