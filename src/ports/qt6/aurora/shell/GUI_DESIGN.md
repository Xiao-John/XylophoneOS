# GUI Design and Implementation Notes

## 1. Scope and design intent

The active UI is a native Qt Widgets desktop-shell prototype. Components are ordinary `QWidget` subclasses and child widgets. Painting, layout, SVG decoding, timing, input handling, and easing use Qt APIs; no external UI framework is involved.

The design follows the supplied Example Window reference: a wallpaper fills the desktop, a compact Dock sits at the bottom, a centered sample window has a light title bar and black content surface, and a transparent status strip sits at the top. Interactive surfaces use rounded geometry and eased transitions. Geometry is derived from a 1024x768 reference canvas unless a component has a separately documented rule.

## 2. Runtime composition and ownership

`main.cpp` creates the `QApplication` and the top-level `Background` widget. `Background` loads the configuration and owns these child surfaces:

1. `WindowEdge`, the sample application window.
2. `ApplicationBrowser`, created lazily when the Dock expansion control is activated.
3. `Docker`, the bottom application launcher and running-state display.
4. `Status`, the top clock strip.

Qt parent ownership controls lifetime. The sample window is a child of the desktop canvas, not a separate native top-level window. `WindowTransition` is a transparent, mouse-transparent sibling overlay used to animate a captured window image while the real window is hidden or resized. `Background::raiseShellLayers()` restores the shell stack in browser, Dock, then status-strip order. Window activation emits a stacking request so the shell remains above the sample window.

The main event flow is:

```text
Dock app click -> Background::activateApplication
                       |-- running app: minimize
                       |-- minimized app: restore from Dock icon
                       `-- closed app: launch from desktop center

Dock expansion -> ApplicationBrowser::open
App tile click -> ApplicationBrowser close transition
                   `-- applicationLaunched -> Background activation
```

## 3. Coordinate system and responsive sizing

The application currently treats the `Background` widget dimensions as its desktop canvas. Its configured size is not automatically changed to the physical monitor size. Widget-local coordinates use a top-left origin; `QRect` right and bottom edges are inclusive, so transition and drag calculations should continue to use Qt rectangle semantics.

The shared reference scale is:

```text
scale = current desktop height / 768
```

When the background image is drawn, it is stretched to the full desktop widget rectangle. The image's aspect ratio is therefore not preserved by the current implementation.

### Dock proportions

For desktop height `H`, define `s = H / 768`:

- Dock surface height: `63s` pixels.
- Icon side: `0.7142 * Dock height`.
- Horizontal gap and outer icon inset: `0.1778 * icon side`.
- Rounded surface corner radius: `13s` pixels.
- Bottom inset: `0.007 * H` pixels.
- Dock width is computed from the count of Dock entries, icon side, gap, and two outer insets.
- The Dock is horizontally centered in the desktop canvas.

The leftmost `muti` control is always reserved by `Docker`. Configured front apps follow it. `addAppToDock()` places newly selected apps before the `trash` entry when that entry exists.

### Status strip and maximized area

The status strip is `28s` pixels high. Its clock content uses a `12s` pixel font and `12s` left/right insets. A maximized `WindowEdge` uses the desktop rectangle below the status strip, not the full canvas. The strip paints no background; the wallpaper remains visible beneath it.

### Example Window proportions

At reference scale, a new Example Window is 418 by 418 pixels. Its title strip is `40s` pixels high, its corner radius is `12s`, and its resize edge threshold is `6s` pixels with a minimum of 4 pixels. The initial window is centered by `Background` after configuration has set its desktop dimensions.

### Application browser proportions

The application picker recomputes a fit scale from the smaller of `width / 1024` and `height / 768`. Search width, grid icon side, tile height, spacing, heading size, and vertical placement use that scale. The grid reserves scrollbar width before calculating columns so that the number of columns does not jump when the content becomes scrollable.

## 4. Component behavior

### Background

`Background` is the desktop canvas and integration point. It resolves `basicconfig.json`, applies positive configured dimensions, loads the optional image, passes the image to `Status` for contrast sampling, constructs shell widgets, connects their signals, and handles resize propagation. It does not implement application-specific contents for the placeholder Dock entries.

### Dock (`Docker`)

`Docker` reads the `docker` object, creates the reserved `muti` item followed by `frontapps`, and renders the rounded translucent surface. Each `DockIconButton` paints its SVG through `QSvgRenderer` with a rounded clipping path. The icon's stable base geometry is separate from the vertical hover lift so status marks remain centered under the unlifted icon slot.

Hover raises an icon by 10% of its side using a 154 ms `InOutCubic` animation. The name label is a separate translucent capsule placed above the Dock. Light and dark palettes use the existing `#DEDEDE` and `#3A3A3A` surface colors.

Application status is one of `Closed`, `Running`, or `Minimized`:

- `Closed`: no marker.
- `Running`: a rounded line centered below the icon, 30% of icon side in length and 6.5% in thickness.
- `Minimized`: the same marker collapses to a small round dot, 6.5% of icon side in length.

The marker transition uses a 260 ms `InOutCubic` animation. Its opacity and length are animated independently from the icon hover and insertion animations.

When auto-hide is enabled, a 50 ms pointer poll checks the desktop bottom edge and Dock bounds. Leaving both starts a 400 ms delay, followed by a 300 ms `InOutCubic` slide below the canvas. The Dock stays revealed while the app browser is open. Moving the pointer within the bottom 12 scaled pixels or over the revealed Dock brings it back.

### Application browser

The app browser loads `docker.allapps`, removes case-insensitive duplicates, sorts names alphabetically, and groups tiles by the first character. Non-Latin or non-A-to-Z initial characters use the `#` group. The search field filters by case-insensitive substring and receives focus only after the user clicks it. Escape or a click on the empty browser surface starts dismissal; an app tile starts dismissal and then emits `applicationLaunched` after the transition finishes.

Opening captures the desktop once, creates a blurred copy once, and crossfades the cached images while dimming the surface. It does not blur the desktop again on every animation frame. The app tiles, captions, headings, and search field share the transition progress. Opening uses 455 ms with `OutCubic`; closing uses 266 ms with `InOutCubic`. Reversing a transition uses the current progress as the new start value.

### Status

`Status` displays local system time and an English date string using `HH:mm   yyyy/M/d   ddd`, such as `13:11   2026/11/8   Sun`. A one-second timer refreshes the text; seconds are intentionally omitted from the displayed format.

The clock label samples 48 by 8 points from the configured wallpaper beneath its text, computes average linearized sRGB luminance, and chooses whichever of black or white has the stronger contrast against that average. A thin translucent outline in the opposite color helps preserve legibility over local wallpaper detail. No clock panel background or right-side controls are painted.

The right side is reserved in code comments for future shell controls, such as volume, clock/calendar actions, and input-method selection. These controls do not exist yet.

### Example Window (`WindowEdge`)

The window paints one rounded silhouette and clips both surfaces to it. The title bar is light gray, the content area is black, and all four outer corners remain transparent outside the rounded path. The title is centered in the horizontal space remaining after accounting for the controls.

Three right-aligned controls minimize, maximize/restore, and close the sample window. Hover widens a control from 22 scaled pixels to a label width derived from the word and font metrics. The right edge remains fixed, which shifts only controls to its left. Symbol/word opacity and width use a 260 ms `InOutCubic` transition. Control labels are bold.

The sample window can be moved by dragging its title strip. It can be resized only from its left, right, or bottom edges, including the lower corners. Minimum dimensions are 280s by 160s, bounded by the available desktop rectangle. Top-edge resizing is deliberately unavailable.

Maximize and restore resize the live QWidget and its child controls over 380 ms with `InOutCubic`. The title height remains proportional during the transition; a stretched full-window snapshot is not used for this operation. A window animation guard prevents concurrent maximize/restore requests.

Launching a closed window animates a snapshot from the desktop center. Minimization animates it toward the app's Dock icon; restoring a minimized window animates from the Dock icon. Launch and restore use `OutCubic` over 380 ms; minimizing uses `InOutCubic` over 320 ms. The Dock icon rectangle is queried when the animation starts so the animation follows the current Dock layout.

## 5. State and animation reference

### Window states

| State | Meaning | Dock marker |
| --- | --- | --- |
| `Closed` | The sample window is hidden after construction or close. | None |
| `Running` | The sample window is open or opening. | Rounded line |
| `Minimized` | The sample window has completed or is completing minimization. | Dot |

`WindowEdge::stateChanged` synchronizes the Dock marker. Maximization is a separate boolean because a maximized window remains `Running`. Clicking its Dock entry while running requests minimization; clicking it while minimized requests restoration.

### Transition ownership

Each component owns the animation it needs:

| Transition | Owner | Easing and nominal duration |
| --- | --- | --- |
| Dock icon hover lift | `DockIconButton` | `InOutCubic`, 154 ms |
| Dock app insertion and recenter | `Docker` | `OutCubic`, 364 ms |
| Dock marker state change | `DockIconButton` | `InOutCubic`, 260 ms |
| Dock auto-hide/reveal | `Docker` | `InOutCubic`, 300 ms after 400 ms hide delay |
| App browser open | `ApplicationBrowser` | `OutCubic`, 455 ms, scaled by remaining progress |
| App browser close | `ApplicationBrowser` | `InOutCubic`, 266 ms |
| Window launch/restore | `WindowEdge` | `OutCubic`, 380 ms |
| Window minimize | `WindowEdge` | `InOutCubic`, 320 ms |
| Window maximize/restore | `WindowEdge` | `InOutCubic`, 380 ms |
| Window control hover expansion | `WindowControl` | `InOutCubic`, 260 ms |

Animations that can be reversed stop the active `QVariantAnimation` and use its current progress or geometry as the next transition's starting point. This avoids restarting from a stale endpoint.

## 6. Configuration contract

The runtime JSON currently has this shape:

```text
root
  background
    width: positive integer
    height: positive integer
    image: path relative to basicconfig.json directory
  docker
    frontapps: ordered app-name array for the initial Dock
    allapps: app-name array displayed by the app browser
    icon: app-name to SVG-path object
```

Icon paths are resolved relative to the config file's directory. Empty or missing icon paths use `icon/unknown/unknown_<FIRST_LETTER>.svg`. The icon map is shared by the Dock and application browser. A missing image currently produces a warning; the app continues without that wallpaper.

JSON does not support comments, so field explanations belong in this document rather than inside `basicconfig.json`.

## 7. Visual and asset conventions

- Dock light surface: `#DEDEDE` at 50% opacity; dark surface: `#3A3A3A` at 50% opacity.
- Dock has no outline.
- The sample window content is black; the title bar is `#E6E6E6`.
- Close controls use `#F45B63`; other window controls use `#BFBFBF`.
- SVGs are runtime assets. The Dock loads them from disk through `QSvgRenderer`.
- `icon/unknown/unknown_A.svg` through `unknown_Z.svg` provide the letter fallback family.
- `muti` is a reserved Dock control and is created from `icon/muti.svg`, regardless of the configured front-app list.
- Keep `icon/` runtime assets synchronized with regenerated files under `assets/icon/`.

The reference coordinate system is based on 1024x768 and uses the display height as the primary scale. The current background image is stretched to the canvas; icon source images are vector and therefore remain crisp when resized.

## 8. Build and runtime deployment

The CMake target is `GUI-Desktop`. The build copies `basicconfig.json`, `background/`, and `icon/` to the binary directory. On Windows, the post-build command runs the Qt kit's `windeployqt` with compiler runtime deployment enabled and translations disabled. Keep the Qt deployment DLLs, platform plugins, configuration, and copied assets next to the executable when distributing a build.

The checked-in translation source currently contains no translated strings. Visible shell labels are primarily English. Translating user-facing strings should add source entries and update the translation catalog rather than adding translated text to design comments.

## 9. Validation guidance

At minimum, build the CMake target after changes. For visual or interaction changes, inspect both the normal 1024x768 layout and at least one larger canvas. Verify:

- All four Example Window corners stay transparent and rounded.
- Maximize and restore preserve the title-bar height throughout the animation.
- The window resizes from left, right, and bottom edges but not the top.
- Running, minimized, and closed states map to line, dot, and no Dock marker.
- Auto-hide, bottom-edge reveal, Dock stacking, and app-browser coexistence remain synchronized.
- Search, captions, grouped application layout, escape dismissal, and repeated open/close all remain usable.
- Wallpaper-aware clock contrast works with both bright and dark images.

An optional local integration harness can live under `build/window-check`; it is a developer artifact, not a product target or installed component.

## 10. Current prototype boundaries

- The desktop widget uses configured dimensions; it is not yet a monitor-spanning desktop manager.
- File, Settings, Browser, and Trash entries do not yet launch complete applications.
- Closing the sample window hides it and clears its Dock marker. The object remains owned by `Background` so the Dock can reopen it.
- The Dock's auto-hide pointer tracking is scoped to the application's desktop canvas.
- Status-strip controls are reserved for future work and are intentionally absent.
- No persistence layer stores Dock order, open windows, window positions, or user preferences.
- Window snapshots are used for launch/minimize/restore animation; maximize/restore changes live geometry.
