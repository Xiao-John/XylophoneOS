# 0103 Application-local SSG in Notes and Browser

2026-10-30. **PASSED_SCOPED_READONLY_PROTOTYPE**. No cross-process scene/action
transport or production authority is implemented. Model output never grants rights.

Notes exposes its real QWidget hierarchy and targeted document text/selection/
scroll state through an explicit synthetic-data `--ssg-probe` mode. Browser reads
real liteHTML/Gumbo elements/text, computed display and actual rendering fragments;
its small read-only upstream accessor is applied to a verified pristine build copy.
Body/link filtering respects the 30ms cap rather than treating partial traversal
as complete. Native tree queries remain available with explicit capped status.

Fresh guest checks cover read-only stability, actual edit diffs, hidden/occluded
and password controls, bounded text, resource denial followed by working GUI,
real link geometry/hit, scroll visibility, navigation/reload epoch invalidation,
unsupported canvas refusal and normal/killed source cleanup. The deterministic
host mock consumes an actual guest snapshot; only the fixture's explicit local
host authorization button executes a bound, expiring, one-shot request. Unknown
external effects remain UNKNOWN and are not replayed. Notes/Browser actions remain
read-only, with cross-process execute/wait/verify BLOCKED / NOT_RUN.

The existing merged candidate navigation repair's affected Notes/Browser functional
and lifecycle gates now pass on the exact new combination, including save/sync/
reboot bytes and failing-load history/tab/scroll preservation. xsh and real dash
launch applicable probes; dash's missing session delegation is tested as a real
failure, not worked around by privilege expansion.

Full traversal originally capped before requested content; an incomplete serial
line was initially parsed too early; old browser anchor logging occurred before
final layout. Original failures are retained. Content filters, framed receiving
and post-layout real-fragment observation fix those causes without relaxing gates.

Host OCR reference matches one synthetic visible link's actual SSG fragment;
its first measured request is 62.54s, with initialization/load contributions not
isolated. This is HOST_ONLY, not a guest OCR port or fair latency ranking. The
minimal AX-style projection is not a real AX service or equivalent attribute set.
Prefix-only document text, unsupported custom graphics, absent cross-origin engine
support and unknown compositor occlusion are explicit coverage limits.

Owning [SSG contract](../contracts/semantic_scene_graph.md),
[G2-Scout proposal](../contracts/aurora_compositor_proposal.md),
[LP0 matrix](../plans/localpilot_xos_lp0.md) and
[guest evidence](../reports/aurora_glass_v2_20261030/ssg/README.md).
Private LocalPilot audit metadata is outside this checkout; no private source,
credentials, configuration, app, workspace or model is copied/changed.

Next: review generic authenticated peer transport/discovery/revocation before any
aggregator. Add bounded text-range/current-visible-text APIs, custom providers and
subscriptions only with real consumers/quotas; do not claim universal GUI semantics.

Frozen SSG report: [scoped evidence](../reports/aurora_glass_v2_20261030/ssg/README.md).
The combined qualification index is supplied later by the Desktop review unit.
Base freshly fetched/rechecked upstream `3377dbf35bdb43d850c9a2b8e8076da3be146f3d`.
Current system build `7ccd5871c0c00297`, image SHA256
`165686bb0de0b0b2f33645ede2cf10c2badb25ea363f3ef57ed74641503b0b08`.
QtBase 6.8.3; one core/512MiB/800×600/QEMU11.1.2 TCG. The matching frozen E17
threading SDK and Qt Core/Gui/Widgets archives are rehashed before target builds.
17 existing shared/SDK headers were compared: 16 exact, one additive unused
execution receipt helper; no system ABI/layout/opcode changes are made here.
All target build commands, tool/archive/SDK/ELF/image hashes, screenshots and raw
logs are frozen. Tests use only dedicated synthetic FAT disks. No Release.
