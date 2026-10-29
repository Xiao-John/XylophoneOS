# Aurora Desktop — G0/G1 userland prototype

One native full-screen Surface, optional Aurora library, no AI required to operate.
This is not a window manager or cross-process compositor. Midnight Current is the
user-selected refinement priority; Daybreak and accessibility modes remain usable.

## Build

Use the matching frozen Qt 6.8.3 Widgets/Core/Gui build and threading SDK described
in [E17](../../../docs/plans/qt_e17_implementation.md). Do not mix Qt archives or
SDK runtimes. These builders validate SDK hashes and record full commands/inputs.

```sh
python3 src/ports/aurora_desktop/build.py \
  --sdk "$SDK" --qt-build "$QT_BUILD" --qt-source "$QT_SOURCE" \
  --host-qt "$HOST_QT_683" --binutils "$TARGET_TOOLS" \
  --output build/aurora_desktop/target
python3 scripts/build.py --output-dir build/aurora_desktop/system
```

Outputs: `desktop/desktop.elf`, `studio/studio.elf`, `semantics/semantics.elf`,
`render/render.elf`, `session.elf`, `compositor_gap.elf` and hash receipts.
Notes uses `src/ports/qt6/build_widgets_fixture.py`; Browser has its own
`src/ports/aurora_browser/build.py`. Both must use these same Qt/SDK inputs.

Install the ELFs on a **dedicated test FAT disk** as `/bin/desktop.elf`,
`/bin/session.elf`, `/bin/studio.elf`, `/bin/notes.elf`, `/bin/browser.elf` and copy
the public Browser fixtures into `/web/`. No host disk/partition is used.

Boot the generated image with that test disk using the existing QEMU runner.
At the serial console:

```text
run
display-start
exec-driver /bin/session.elf
```

`exec-driver` is the existing explicit bounded child-spawn grant entry; its name
does not grant MMIO/DMA/device access. The ordinary session parent starts the
desktop without child-spawn authority. App selection returns a bounded request
through normal exit status; the parent validates its whitelist, waits for the
desktop to release its Surface, launches the selected independent application,
waits and restores the desktop. No application-specific kernel operation exists.
Unprivileged startup without that explicit grant fails honestly.

Direct `exec-file /bin/desktop.elf` is a preview. It can exercise native settings
and controls, but app launch explains that a session parent is needed.
Settings are session/process local. A real live settings broker is not implemented.
Shell appearance is retained across child launches; legacy Notes/Browser still
use their existing E17 dark shells rather than claiming full G3 theme migration.

## Interaction

- Dock: Home, Apps, Studio, Settings, Quality, Hide. Hide affects the workspace
  panel, not a separate application window. Home restores it.
- Ctrl+, opens appearance; Ctrl+L opens the application launcher; Ctrl+D switches
  the two proposals; Escape returns Home, then exits; Ctrl+Q exits directly.
- Appearance: theme, high contrast, reduce transparency/motion and wallpaper.
- Quality: High/Balanced/Low/Safe or fully disable glass. Effective fallback is
  recorded separately when the cache cannot fit or generation exceeds its budget.
- Studio: real standard fields/editor/buttons, in-surface menu and notification.
  Native separate popup windows, global file dialogs and notifications await G2/G3.

The cursor and glass are owned by this application. They cannot read another
process's pixels. All timing/waits reuse existing Qt/XOS time domains.

## SSG / Intent probes

`notes.elf /synthetic-note.txt --ssg-probe` and `browser.elf --ssg-probe` explicitly
enable test-only serial scene export; Ctrl+I queries the scene. Normal launches
do not export it. Notes provides an initial bounded tree then document-role
queries; Browser queries its actual body text/link model and render fragments.
`semantics.elf` is the independent standard-Widgets provider and local grant
fixture. The deterministic mock consumer runs independently in the test harness;
it proposes data and cannot create a Grant. The fixture's explicit authorization
button tests local execution/verification only.

See the [SSG contract](../../../docs/contracts/semantic_scene_graph.md),
[G2 gap proposal](../../../docs/contracts/aurora_compositor_proposal.md),
[design/quality rules](../../../docs/design/aurora_glass_v2.md) and
[LP0 matrix](../../../docs/plans/localpilot_xos_lp0.md). Cross-process AI authority,
scene aggregation, real WebView/Tauri and LocalPilot operation remain unimplemented.

## Reproduce guest tests

```sh
python3 tests/aurora_desktop_guest.py --image "$IMAGE" --target "$TARGET" \
  --output build/aurora_desktop/interactive --case interactive
python3 tests/aurora_platform_guest.py --image "$IMAGE" --target "$TARGET" \
  --apps "$APPS" --output build/aurora_desktop/ssg --case semantic
```

Each output directory must be new. Runners verify ELF receipts, use synthetic
fixtures, actual QMP PS/2 events and QEMU scanout, and compare exact process
resources. The work log lists failures, actual qualified artifacts and remaining
gates. Existing system/Qt qualifications remain bound to their original inputs.
Public Qt binary distribution/member/license/relink qualification is not granted.
