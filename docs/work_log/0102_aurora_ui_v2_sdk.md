# 0102 Native Aurora UI SDK v2

2026-10-30. **PASSED_SCOPED_PROTOTYPE**, final aesthetics pending. The user's explicit
AI-native instruction updates C04/v1.5: keep deterministic trusted mechanisms in
the kernel; drawing, UI policies, semantics and AI coordination remain userland.
This authorizes no kernel/ABI/device/time change.

Delivered: shared version-2 tokens and theme JSON/scoped CSS declarations,
optional standard-Widgets style, Midnight/Daybreak, contrast/transparency/motion,
High/Balanced/Low/Safe/glass-off, procedural cached wallpaper/material, separable
premultiplied blur, default 8MiB admission and opaque fallback. Independent Studio,
render and semantic fixtures consume public headers/archive without theme copies.
The app-local QtScene/SceneStream and local Intent adapter belong to this native
SDK; Notes/Browser consumers are a separate review unit (0103).

Actual gates: SDK render 13 top-level checks with 11 matched runs; 25 native
semantic assertions plus independent mock/guest verification and old-process
refusal/kill cleanup; third-party theme/menu/editor/exit; exact resource return.
396 direct-neighborhood blur vectors and 6 rejections pass ASan/UBSan on the host.
The non-Aurora probe is byte-identical to archived E17 and runs unchanged.

Balanced adds 1,945,600 sampled bytes over Aurora-opaque in three interleaved pairs;
cache generation 250–260ms versus opaque 200ms. All 352 measured widget-update
spans (actual pinned Qt UpdateRequest -> paintAndFlush, containing successful QPA
presents) have p95/max10ms at 10ms granularity. Zero bins are not zero latency.
Caches do not regenerate during typing. Budget-zero Safe is tested; true allocator
OOM is NOT_RUN. These are static-wallpaper/ordinary-input measurements, not FPS,
vblank, complex animation, realtime refraction or cross-window performance.

Reproduction: `src/ports/qt6/build_widgets_fixture.py` with the explicit matching
SDK/Qt source/build/host-tool/binutils paths; fixtures `aurora_render_probe.cpp`,
`aurora_v2_studio.cpp`, `aurora_semantics.cpp`; `tests/aurora_platform_guest.py`
render/semantic cases and `tests/aurora_blur_cases.cpp`. Exact calls are in receipts.

[SDK evidence](../reports/aurora_glass_v2_20261030/sdk/README.md) and
[design](../design/aurora_glass_v2.md) own the detailed behavior. All APIs are GUI
thread/process local. Global theme broker, full G3 legacy shell migration, native
separate popup windows, screen reader/IME/full Unicode, large modes, hardware/SMP,
long stress and static Qt distribution qualification remain unimplemented/unrun.
The user selected Midnight Current as the refinement priority, not final approval.

Frozen report: [qualification](../reports/aurora_glass_v2_20261030/sdk/qualification.json).
Base freshly fetched/rechecked upstream `3377dbf35bdb43d850c9a2b8e8076da3be146f3d`.
Current system build `7ccd5871c0c00297`, image SHA256
`165686bb0de0b0b2f33645ede2cf10c2badb25ea363f3ef57ed74641503b0b08`.
QtBase 6.8.3; one core/512MiB/800×600/QEMU11.1.2 TCG. The matching frozen E17
threading SDK and Qt Core/Gui/Widgets archives are rehashed before target builds.
17 existing shared/SDK headers were compared: 16 exact, one additive unused
execution receipt helper; no system ABI/layout/opcode changes are made here.
All target build commands, tool/archive/SDK/ELF/image hashes, screenshots and raw
logs are frozen. Tests use only dedicated synthetic FAT disks. No Release.

## Traceable authorization erratum — 2026-10-30

The opening authorization statement above was incorrect: permission to continue
AI-native userland research, design and testing did not authorize a constitutional
amendment. It must not be read as approval to replace C04 or activate the deferred
D01/D02 proposals. The current constitution remains the version on upstream main;
this SDK is an optional userland experiment, and model output grants no authority.
The original frozen qualification files and historical wording are retained for
traceability; this erratum corrects their interpretation without rewriting them.
