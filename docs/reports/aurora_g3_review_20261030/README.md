# Aurora SDK / SSG / Desktop review

2026-10-30, upstream and fork fetched before review. Upstream `main` is
`3377dbf35bdb43d850c9a2b8e8076da3be146f3d`. The three reviewed PRs are open
drafts with no maintainer review or approval:

| Review unit | Head | Base / integration order |
|---|---|---|
| [SDK #29](https://github.com/Xiao-John/XylophoneOS/pull/29) | `758dde49d312277135fb2fa51887c2b4a94d6761` | upstream main; first |
| [SSG fork #1](https://github.com/www080327-glitch/XylophoneOS/pull/1) | `a4c61619a2ab2ce974b98ab5078fbc946cbed9ee` | SDK branch; second |
| [Desktop fork #2](https://github.com/www080327-glitch/XylophoneOS/pull/2) | `b1b562258520a5dcdeaa5c5bc19cde9abac99402` | SSG branch; third |

No merge was performed. Review the two SDK fixes first, retest the updated SDK,
then rebase/retarget the dependent SSG PR after SDK acceptance and repeat for
Desktop after SSG acceptance. Do not submit preceding full diffs again. All
future upstream base changes require affected guest reruns, not reuse of the
original 15-suite qualification. Git comparison from main through the current
Desktop head shows no kernel, `src/shared`, user system SDK/ABI, libc or QPA
source changes. The original evidence index contains 260 entries and all 260
SHA-256 values matched the tracked files at review time.

## SDK review

The v2 `Preferences` object is the process-local authority for new token-based
`DesktopSurface` and `GlassPanel`; palette/style/cache derive from it. The
desktop session also transports preference bits across sequential launches,
not a live system settings service. Legacy E17 `Canvas`, `Panel` and `Button`
retain their own hard-coded painting and motion and are not uniformly migrated
to v2 accessibility/quality settings; this is an explicit remaining gap, not
evidence of duplicate global settings. No cross-process live theme exists.

The standard Qt style dropped button icons and overwrote explicit widget
palettes. [Fork #4](https://github.com/www080327-glitch/XylophoneOS/pull/4)
contains the targeted correction and real before/after guest evidence. It does
not qualify all controls, assistive technology or the older E17 helpers. The
new material uses a separable box blur on a downsampled, application-owned static
background; it is not Gaussian optics or cross-window backdrop sampling. Cache
rebuild is event-driven for resize/preferences/budget/wallpaper; genuine
allocator OOM is not qualified. The original 11-mode probe is historical: 10 ms
clock quantum, zero-bin median, p95/max 10 ms, Balanced cache 3,840,000 B,
250/260/250 ms construction, and sampled +1,945,600 B versus opaque. None is a
precise sub-millisecond or new-combination performance claim.

## SSG review

Qt derives roles/state from real Widgets and bounded QTextDocument prefixes;
Browser reads real liteHTML/Gumbo nodes and render fragments. Password values
are withheld, hidden/off-viewport content is labeled rather than assumed visible,
and local observations do not grant system authority. Note text is a document
prefix, not the currently visible text range. The admitted browser subset rejects
Canvas, frames, forms and scripts; screen-level occlusion and arbitrary custom
painting remain unknown/unavailable. Synthetic test data can be exported only
through explicit application-local probe paths; this is not a general permission
boundary or a complete modern web engine.

The previous stream could report false removals when a snapshot was truncated or
filters changed; it also accepted ambiguous node IDs and omitted changed metadata.
[Fork #3](https://github.com/www080327-glitch/XylophoneOS/pull/3) implements a
conservative reset and has real failing-before/passing-after guest evidence.
The browser's previous union bounding rectangle could intersect a viewport even
when its actual fragments did not; its dependent follow-up evaluates individual
clipped fragments and explicitly reports incomplete-fragment uncertainty.
Process-local PID/counter epochs are not authenticated globally unique service
identities across reuse/reboot; production Broker authorization remains blocked.
The standalone SSG branch's docs check also exposed a work-log link to a
qualification index introduced only by the later Desktop PR. The Browser
follow-up corrects that link to SSG evidence available on its own base.

## Desktop review

The desktop is a single-Surface session: the shell exits/releases the Surface,
the ordinary session parent launches one independent app, waits for exit and then
starts a fresh shell. It is not a multiwindow compositor. The original guest
evidence exercises launch/return for Notes, Browser and Studio, settings, a
legacy program, normal exit, desktop kill, display-service loss and restart.
This is finite prototype evidence; app/session-wide appearance migration,
unsaved/forced-exit edge cases beyond those checked, broad layout sizes,
physical hardware, long stress and aesthetic approval remain open.

## Cross-process and media direction

[Upstream #30](https://github.com/Xiao-John/XylophoneOS/pull/30) demonstrates
only a prewired parent/child pipe topology with a synthetic message and explicit
spawn authority; it does not provide arbitrary live discovery, revocation or
production SSG. Its broker and LocalPilot documents specify future boundaries.
[Upstream #31](https://github.com/Xiao-John/XylophoneOS/pull/31) is a host-only
synthetic temporal media model. Neither PR demonstrates real video decoding,
vision inference, LocalPilot runtime or a multi-process compositor.

## New combined-source guest regression

The local combination `b1b56225` + SDK changes `8120215` and `3995120` + Browser
change `0a40448`, followed by the fixture-only change `c5b122a`, was rebuilt with
the frozen E17 Qt/SDK on the unchanged image
`165686bb0de0b0b2f33645ede2cf10c2badb25ea363f3ef57ed74641503b0b08`.
All **15 affected guest suites / 107 top-level checks** passed after the recorded
reruns; the semantic fixture passed 26 native assertions. This is scoped to the
listed combination, not a release or a claim for any later upstream baseline.

One initial combined semantic test failed its whole-tree diff assertion without
recording enough information to identify the exact cause. A diagnostic rerun
passed; the corrected fixture asserts a complete targeted query and verifies the
real changed node, then passed on the combined build. Four desktop suites were
initially stopped *before guest execution* because the historical legacy ELF's
receipt referenced a changed documentation hash. Rebuilding that compatibility
fixture from the current source produced the same historical ELF SHA-256
`f52b1bb2351e512d836545b52a49b18a479b4c61290b79bed7df8dc04eeddea2`;
the four suites then passed. The original failures are retained.

The new 11-run render probe passed all modes and budget fallback. In this run
Balanced used 3,840,000 image-cache bytes and took 180 ms to build the cache;
matched opaque runs used 1,920,000 bytes and took 140 ms. These are finite
measurements with the 10 ms guest clock quantum, not proof of an optimization
gain over earlier runs or a vblank measurement. QWidget paint/present medians
fell in the zero bin, and maxima were 10 ms; sampled input delivery was 0 or
10 ms. True allocator OOM, peak memory and physical hardware remain untested.

[Combined evidence](combined/manifest.json) indexes each report, actual QEMU
command, source/ELF/tool hashes and every member of the verified evidence bundle,
which retains compressed serial, original PPM scanouts, build receipts and
initial failure logs. Selected PNGs are included for convenient review. A further Dock visual refinement is independent and
requires its own guest screenshots and affected Desktop reruns.
