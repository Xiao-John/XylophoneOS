# Xylophone Aurora Glass v2

2026-10-30. G0/G1 prototype. Visual approval remains **PENDING USER REVIEW**.
The actual guest evidence and qualified scope belong to the accompanying work log;
this design document does not grant compositor, accessibility or release qualification.

## Design reasoning and original proposals

Apple's [Materials](https://developer.apple.com/design/human-interface-guidelines/materials),
[Meet Liquid Glass](https://developer.apple.com/videos/play/wwdc2025/219/) and
[design-system presentation](https://developer.apple.com/videos/play/wwdc2025/356/)
inform our separation of navigation from reading content, restrained ambient tint
and concentric geometry. The macOS guidance favors compact controls in dense
desktop areas; the visionOS discussion motivates luminance restraint for readable
foregrounds. These are public design principles, not an implementation of Apple's
material. [GNOME's adaptive guidance](https://developer.gnome.org/hig/guidelines/adaptive.html)
informs the constrained-screen-first layout and controlled sidebar width. These
sources were consulted on 2026-10-30; no Apple/KDE/GNOME assets or fonts are copied.

User review on 2026-10-30 selected **Midnight Current as the refinement priority**.
This selects direction, not final aesthetic acceptance. Daybreak remains available.

Two original compositions are implemented in the same native guest application:

| Proposal | Composition | Material/color intent |
|---|---|---|
| Midnight Current | Floating bottom Dock, broad heading and centered workspace | Ocean/indigo with cyan primary controls, violet ribbons and small warm environmental light; navy reading surfaces |
| Daybreak Atelier | Narrow left navigation rail, offset heading and larger vertical work area | Cool daylight, lavender horizon, deep blue ink and teal emphasis; lighter, more restrained glass |

The wallpaper is procedural QPainter code. The eight-segment continuous-corner
path is the existing original Aurora curve. Inner radii subtract their inset from
outer radii. No SF font, SF Symbols, Apple wallpaper or proprietary icon is used.
DejaVu Sans remains the existing pinned, licensed font. New dependencies: none.
The inherited E17 bitmap and helper APIs remain available for existing consumers.

## Public userland interface

`libXosAurora.a`, token/API version 2:

```cpp
QApplication app(argc, argv);
aurora::initialize(app);                 // explicit opt-in
auto p = aurora::preferences();
p.scheme = aurora::Scheme::daybreak;
p.quality = aurora::Quality::balanced;
aurora::set_preferences(p);              // GUI thread, this process only
aurora::desktop_surface surface;
auto *panel = new aurora::glass_panel(&surface);
// Standard QPushButton/QLineEdit/QPlainTextEdit reuse the selected native style.
```

`theme.hpp` is the versioned source of semantic colors, body/caption/title sizes,
8px grid, insets, panel/control radii, control height, focus/danger roles, blur
parameters and motion policy. `theme_json()` exports a bounded read-only descriptor;
`theme_css_variables()` exports CSS declarations for an explicitly scoped app host.
Neither provides WebView transport or modifies any web document's CSS.

| Capability goal | Current reusable implementation / boundary |
|---|---|
| window / panel / toolbar / sidebar | desktop_surface + glass_panel + Qt layouts; one native top-level Surface |
| button / field / editor / scroll view | Standard Widgets + Aurora QProxyStyle/QPalette; real editing/focus/selection/scrolling |
| Tabs / dialog / notification | Standard child controls and application-local panels; no system notification/dialog broker |
| Menu | Keyboard-accessible in-surface child controls; independent native popup windows remain unsupported |
| Theme settings | One process and session parent retain preferences; cross-process live broker is PROPOSED, not implemented |
| Third-party integration | Optional opt-in; independent Studio links the archive without copying its source |
| Legacy apps | No opt-in means no global style installation; existing QPA/v1 lifecycle remains |

Legacy E17 canvas/panel/button are application-specific compatibility helpers with
their original dark artwork; they are not silently declared v2/global-theme migrated.
Notes/Browser retain those shells this round, with affected functional regressions
checked separately. Full G3 visual migration and a common settings broker remain work.

## Quality, fallback and cost

| Requested quality | Static software material | Cache behavior |
|---|---|---|
| High | 2× downsample, radius-6 separable box blur, smooth reconstruction | Fine reference profile; slow generation can select a lower effective quality |
| Balanced | 8× downsample, radius-2 blur | Default cached navigation material |
| Low | 16× downsample, radius-1 blur | Coarser low-frequency material |
| Safe | Opaque native theme, no backdrop blur | Wallpaper cache only when budget permits |

The separable box blur uses clamped edges and rounded premultiplied ARGB channel
means. It is deterministic CPU rendering, not optical refraction or shader/GPU
rendering. High/low differences are measured rather than equated to equal visual
quality. Existing VirtIO-GPU2D is scanout only; C28 debt is not expanded here.

Static wallpaper and softened layers are regenerated on size, palette/material
policy, wallpaper or cache-budget change. Input/caret/focus damage uses Qt's QRegion
and existing QPA clipped presents; typing must not regenerate background caches.
An ordinary child panel moving over the wallpaper resamples the correct source
rectangle. This is still application-local material, not lower-application sampling.
There is no continuously running Aurora animation timer in the new pipeline.

The default image admission budget is 8 MiB, including estimated full images and
three low-resolution blur images. Lower the requested quality before allocation
if it cannot fit. Null image allocation or caught allocation failure selects an
opaque fallback; a zero image budget selects flat Safe output with no image cache.
A blur stage above 250ms requests a lower stage and records requested/effective
quality and the fallback. Actual OOM injection remains a separate gate; explicit
budget denial must not be mislabeled as real host/guest allocator exhaustion.

High contrast forces opaque material and stronger edges. Reduce transparency
removes backdrop sampling. Reduce motion sets transition durations to zero; the
new Shell uses immediate deterministic state changes even in normal mode. Glass
can be fully disabled, selecting the ordinary native opaque theme. These modes
are intentional accessibility/performance options, not claims that full glass
met its cost target. No SIMD or GPU backend is added without measured need.

The render probe uses identical window geometry, wallpaper, controls and PS/2
typing. It compares all qualities, full glass-off and Aurora-opaque controls,
including repeated interleaved Balanced/opaque runs. Existing QPA logs provide
hardware-event-to-GUI delivery and dirty-present timing from the canonical clock.
Cache generation time/bytes, sampled pages/threads, idle flush count and exact
resource return are recorded separately. The independent render fixture also times the public QWidget UpdateRequest call
through the pinned Qt paintAndFlush path, counting only spans containing successful
QPA presents. This includes widget painting and synchronous submission without any
Qt/QPA modification. It is not vblank latency; finite memory samples are not an absolute peak.

## Review checklist

800×600 is the current guest baseline. The two layouts have explicit margins,
bounded rail/Dock geometry and content insets. Larger-mode and responsive rules
exist in layout code but need their own actual guest qualification. Check real
scanout, focus, hover, disabled state, legibility, consistent concentric geometry,
text clipping, menus and reduced modes. User review decides aesthetic acceptance;
programmatic assertions establish functional facts only. screen readers/IME/full
Unicode, global theme negotiation, windows between independent apps, file chooser,
task switcher and global notifications are not implied by this prototype.
