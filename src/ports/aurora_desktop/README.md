# Mobius — G0/G1 userland prototype

One native full-screen Surface, optional Aurora library, no AI required to operate.
This is not a window manager or cross-process compositor. Midnight Current is the
user-selected refinement priority; Daybreak and accessibility modes remain usable.

## Build

Use the matching frozen Qt 6.8.3 Widgets/Core/Gui build and threading SDK described
in [E17](../../../docs/plans/qt_e17_implementation.md). Do not mix Qt archives or
SDK runtimes. These builders validate SDK hashes and record full commands/inputs.

The glibc C/C++ candidate has a separate Qt Widgets build and Mobius entry.
See the [glibc desktop and session reproduction](../../../docs/work_log/8f0020c4_mobius_glibc_widgets_guest.md).

### Build from a relocated Widgets kit

Use the verified Linux arm64 Qt host kit and the unified glibc SDK v2 profile.
The Widgets producer uses the shared QtBase source and configuration from the
[unified Quick build](../qt6/quick/unified_sdk.md), with `FEATURE_widgets=ON`
and `FEATURE_filedialog=OFF`. It installs its own Core, Gui and Widgets headers
and archives. Quick keeps the headers and archives from its Widgets-disabled
build. Both targets can share the QtBase source archive and host generators.

Run the first command with `--check-inputs` to verify the SDK profile,
cross-tools, source and generators without configuring Qt or creating output.
Use a fresh build directory on a Linux filesystem for the build itself.

```sh
python3 -B src/ports/qt6/quick/build_target.py \
  --component widgets --host-kit "$HOST_KIT" --sdk-build "$SDK" \
  --sdk-profile "$PROFILE" --output "$WIDGETS_BUILD" --jobs 2

python3 -B src/ports/aurora_desktop/glibc/widgets_kit.py \
  --sdk-build "$SDK" --sdk-profile "$PROFILE" \
  --qt-build "$WIDGETS_BUILD/qtbase_build" --qt-prefix "$WIDGETS_BUILD/target" \
  --qt-source "$WIDGETS_BUILD/qtbase_source" --host-qt "$HOST_KIT/host_qt" \
  --qtbase "$HOST_KIT/qtbase.tar.xz" --output "$WIDGETS_KIT" \
  --target-receipt "$WIDGETS_BUILD/target_receipt.json"
```

The v2 receiver requires the staged kit and its target receipt. The receipt
binds the effective Qt features, target tree, CMake cache, prepared source,
native generators, cross-tools and SDK profile. The earlier v1 kit format
continues to work with its original SDK and profile.

Move the kit to a new Linux arm64 prefix. The reported manifest digest is
supplied separately to the receiver. The receiver needs the same glibc SDK
profile, matching cross-tools, CMake, Ninja and the Mobius sources. Its build
binds both full widgets-kit trees and the exact application link inputs.

```sh
python3 -B src/ports/aurora_desktop/glibc/build.py \
  --sdk-build "$SDK" --sdk-profile "$PROFILE" --widgets-kit "$MOVED_KIT" \
  --widgets-kit-sha256 "$KIT_MANIFEST_SHA256" --output "$MOBIUS_BUILD"
python3 -B scripts/package_desktop_products.py mobius "$MOBIUS_BUILD/mobius.elf" \
  --session "$MOBIUS_BUILD/mobius_session.elf" --sdk "$SDK" --profile "$PROFILE" \
  --revision "$REVISION" --output "$MOBIUS_XPK"
```

The XPK uses the existing `xos.mobius` package and the public Mobius executable
and session paths. It carries the SDK and Qt notices, the QtBase source lock and
the generated Aurora wallpaper's provenance. The product materials capture
the actual static objects and archives used for both executables. Use the
original locked QtBase archive and the SDK and kit used by the receiver.

```sh
python3 -B src/ports/aurora_desktop/glibc/product_relink.py stage \
  --build "$MOBIUS_BUILD" --sdk-build "$SDK" --sdk-profile "$PROFILE" \
  --widgets-kit "$MOVED_KIT" --widgets-kit-sha256 "$KIT_MANIFEST_SHA256" \
  --qtbase "$LOCKED_QTBASE_ARCHIVE" --output "$MOBIUS_MATERIALS"
python3 -B src/ports/aurora_desktop/glibc/product_relink.py relink \
  --materials "$MOVED_MOBIUS_MATERIALS" --sha256 "$MATERIALS_MANIFEST_SHA256" \
  --output "$RELINK_RESULT"
```

The second command uses the matching target compiler, assembler and linker.
It verifies that both static ELFs reproduce the original receiver link byte
for byte. The existing Curvive wallpaper's license qualification and the
complete public distribution record are separate from the private XPK.
[Acceptance plan](../../../docs/plans/mobius_unified_widgets.md)

### Earlier SDK build

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

Install the ELFs on a **dedicated test FAT disk** as `/usr/bin/mobius.elf`,
`/bin/session.elf`, `/bin/studio.elf`, `/bin/notes.elf`, `/usr/bin/clarke.elf` and copy
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

Direct `exec-file /usr/bin/mobius.elf` is a preview. It can exercise native settings
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
