# Xylophone Notes · Aurora Glass — E17 design study

2026-10-29. Design target, not guest acceptance. Reference floor: the user's supplied
Notes concept. Reviewable composition: [draft](aurora_glass.svg). Final evidence must
be real XOS/QEMU scanout with the application ELF/SDK hashes attached.

## Research and interpretation

Apple's [Meet Liquid Glass](https://developer.apple.com/videos/play/wwdc2025/219/)
describes light shaping, floating controls, responsive highlights and contextual
adaptation. We take the separation of navigation from content and restrained
optical edge cues as design references. This CPU implementation does not implement
Apple's material or its real-time lensing.

[Get to know the new design system](https://developer.apple.com/videos/play/wwdc2025/356/)
explains concentric nesting, compact desktop controls versus prominent capsules,
functional grouping, and content legibility. We use nested radii, a separate Save
capsule, and an opaque reading surface rather than glass behind every text line.
The [Materials guideline](https://developer.apple.com/design/human-interface-guidelines/materials)
is a reference entry; its scripted body was unavailable to the research reader,
so no additional claims are derived from it. These are public 2025 design sources
consulted in 2026, not proof of any unverified 2026 Apple implementation.

## Original design

- 800×600 baseline, 18px outer inset, 32px shell curvature. 156px navigation,
  32px structural gap, 54px floating toolbar, 18px content gap. Reading-card
  radius 28px; content inset 22px. Eight cubic corner segments have tangent
  continuity and zero curvature on joining the straight edge; not a claim of
  reproducing Apple's proprietary curve.
- Midnight ocean/indigo, cyan/violet reflected light, a small peach horizon.
  Original image generation, prompt and hashes are retained with the asset.
  No Apple artwork, logo, SF Symbols, reference pixels or proprietary fonts.
  Xylophone's four-bar mark is drawn in code. Typography: bundled DejaVu Sans.
- Background and softened environment cached on size change. Glass layers sample
  that environment, then apply color absorption, a top sheen, directional edge
  highlights and a small shadow. Text uses a stable nearly opaque navy surface.
  This is cached software composition, without real-time refraction or a compositor.
- Real QLineEdit, QPushButton-derived controls, QPlainTextEdit and scrollbars.
  Current-note navigation focuses the real document; Open/Save/Exit are functional.
  No decorative fake search, collections, rich-text tools or unimplemented counters.
- Hover blends on a 33ms timer only while transitioning; press/focus have separate
  paint states. A button paint over 35ms switches that control to static feedback.
  Input, saving and shutdown never wait on an animation.

## Frozen targets before visual guest measurement

At single-core 512MiB QEMU TCG, 800×600: two backdrop caches ≤4MiB, total new visual
caches target ≤6MiB; sampled process pages target ≤16384 (64MiB), not absolute peak.
Ordinary interaction target median ≤100ms, p95 ≤200ms; dirty present target ≤120ms.
Startup/first raster and deliberate fault stalls are reported separately. These
are engineering targets, not measured results; misses remain visible and trigger
reduced effects or explicit qualification limits, never silently relaxed gates.

Visual checks: real rendered controls and glyphs; consistent insets/curves; no
white/default frames; legible text and selection; correct focus/hover/pressed/
modified/error/confirmation; scroll clipping; display-fault exit and exact resource
return. Host draft is not evidence of these checks.

## 2026-10-30 Aurora v2 continuation

Two native proposals, shared tokens, quality/accessibility fallback and the single-Surface
Shell continue in [Aurora Glass v2](aurora_glass_v2.md). The E17 evidence above retains
its original scope; neither it nor the new Shell implies a cross-process compositor.
