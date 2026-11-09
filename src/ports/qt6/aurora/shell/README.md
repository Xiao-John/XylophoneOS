# Aurora Desktop

This directory replaces the earlier approximate desktop with the five Qt Widgets
components from GUI-Desktop. The design source is [GUI_DESIGN.md](GUI_DESIGN.md)
and its component comments. SHA-256 hashes of the imported source files are recorded
in `upstream.json`. Original icons and wallpaper are preserved under `artwork/`.

## Components and Layers

| Layer / component | Implementation |
| --- | --- |
| Background | Stretches the full wallpaper to fill the screen without cropping or tinting |
| Desktop | Separate transparent desktop layer, reserved for desktop-file interactions |
| WindowEdge | Light title bar, black content, rounded clipping, dragging, left/right/bottom resize |
| ApplicationBrowser | Alphabetical groups, substring search, one-time background blur, launch after close animation |
| Docker | Original icons, specified proportions, hover lift, name capsule, line/dot state, auto-hide |
| Status | Transparent status bar, system time, wallpaper luminance sampling and black/white text contrast |

Launch, minimize, restore, and maximize use the durations and easing from the design.
Maximized windows avoid only the top status bar. The Dock overlays the application
layer and hides/reappears in response to the pointer at the bottom edge.
`window_edge.hpp` forwards to the canonical WindowEdge implementation here.

## XOS Adaptation and Limits

- Aurora does not read `basicconfig.json`. `system_context.h` obtains screen dimensions
  from the QPA screen, which comes from the Interactium handshake. XOS currently reports
  800x600, scaled using H/768.
- The application catalog is an explicit built-in prototype catalog. Only
  `examplewindow` has an implemented window; File, Settings, Browser, and Trash remain
  design entries without pretending to be complete applications. A future system
  application registry can replace the catalog; no such service exists yet.
- The clock reads XOS system time and displays the system's current time zone; it does
  not emulate the host Windows time zone.
- Target Qt 6.8.3 has no QtSvg or PNG decoder. `prepare_assets.py` uses host PySide6/QtSvg
  to render the original SVGs to 192x192 premultiplied-alpha pixels and downsamples the
  full wallpaper to a 1024-pixel-wide BMP. Icon content and wallpaper framing are kept.
  Lossless vector scaling on large displays still requires QtSvg.
- The Dock name capsule is a desktop child widget to avoid a native opaque Tooltip
  window in the current QPA.
- QPA reports the actual pointer position; the Interactium service draws the triangle
  pointer above all clients. The service currently draws only this triangle and does
  not change it for Qt resize or pointing-hand cursor shapes.
- As in the source project, application windows are QWidgets within the desktop.
  Decorations for arbitrary independent-process windows, application registration,
  and desktop-file management are outside this prototype.
- Animation timing matches the design, but actual frame rate is limited by TCG,
  software painting, and chunked IPC transfers. Host Qt performance does not predict
  virtual-machine performance.

## Launch the Deployed Build

Run this from PowerShell at the XylophoneOS repository root:

```powershell
python scripts/run_qemu.py --iso-file --image build/aurora_desktop_rewrite/system/xos-install.iso --vga --work-disk build/aurora_desktop_rewrite/aurora.img
```

At the QEMU serial console, enter:

```text
run
demo quiet
interactium-start
exec-file /AURORA_DESKTOP.ELF
```

Click **E** in the Dock to open Example Window; click it again to minimize, then click
again to restore. The leftmost arrow opens the application menu. Click the search field,
type `example` to filter, and press Escape to dismiss. The window controls on the right
minimize, maximize/restore, and close. After maximizing, move the pointer to the bottom
edge to reveal the Dock. Drag the title bar to move the window; resize from the left,
right, and bottom edges.

`aurora.img` is a separate 512 MiB FAT32 work disk with `AURORA_DESKTOP.ELF` imported.
The system ISO includes the Interactium pointer implementation built for this version;
older ISOs do not draw this pointer in the service.

## Rebuild from Source

The commands below use the cross-compiler, SDK, target Qt, and matching Qt 6.8.3 moc/rcc
already available in this workspace. Host Python needs PySide6; keep using the host
Python when updating PATH so MSYS Python is not selected accidentally.

```powershell
$Python = (Get-Command python).Source
$env:PATH = "$PWD/build/qt_enabled/cross/bin;C:/msys64/ucrt64/bin;C:/msys64/usr/bin;" + $env:PATH
& $Python src/ports/qt6/aurora/build_desktop.py --sdk build/interactium_aurora/current_thread_sdk --qt-build build/interactium_aurora/qt_widgets_build2 --core-build build/interactium_aurora/qt_widgets_build2 --qt-source build/interactium_aurora/qt_widgets_source --host-qt build/qt_enabled/host_qt --binutils build/interactium_aurora/system5/target_tools --generated-qt-build build/interactium_aurora/qt_widgets_build2 --output build/aurora_desktop_rewrite/AURORA_DESKTOP.ELF
$env:NASM = '<configure-local-path>'
& $Python scripts/build.py --output-dir build/aurora_desktop_rewrite/system
```

The build does not replace an ELF already on a disk. To update it, close QEMU using
that disk, create a new work disk, then deploy with
`scripts/work_disk.py NEW_DISK import /AURORA_DESKTOP.ELF NEW_ELF`. Import refuses to
overwrite an existing file. The ELF `.receipt.json` records build commands and input hashes.

## Verification

Run the real-QEMU test:

```powershell
python tests/aurora_desktop_guest.py --iso build/aurora_desktop_rewrite/system/xos-install.iso --disk build/aurora_desktop_rewrite/aurora.img
```

Serial logs, interaction screenshots, and the test result are saved under
`build/aurora_desktop_rewrite/guest/`. The test drives the running ELF with real PS/2
mouse and keyboard input; screenshots do not substitute for execution.

For host Qt verification, use this directory's CMakeLists.txt (Qt Widgets and Qt Test).
Run `prepare_assets.py`, then build `aurora_preview` and `aurora_shell_test`. Test
arguments are the screenshot directory and the DejaVuSans.ttf path. Set screen dimensions
with `-platform offscreen:configfile=SCREEN_CONFIG.json`. Verified sizes are 800x600,
1024x768, and 1366x900. Host preview uses desktop Qt and does not replace XOS verification.
