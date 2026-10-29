# Xylophone Aurora Glass (Qt Widgets 6.8.3)

An opt-in XOS user-space style and visual library. It does not alter QtCore,
Qt Quick, other processes, the display ABI, or the single-surface policy.

```cpp
#include "style.hpp"
QApplication app(argc, argv);
aurora::initialize(app);
```

`initialize()` selects the QProxyStyle, explicit active/inactive/disabled palette
and bundled DejaVu family. Standard QPushButton, QLineEdit, QPlainTextEdit and
QLabel use that theme. The actual XOS QPA/font resource must also be linked.
`aurora.hpp` additionally provides Canvas, Panel, Button and Brand components;
Canvas/Panel cache their own environment layers, and Button adds limited hover
transitions and a measured slow-paint fallback. The software pointer belongs to
that application canvas, not a system compositor.

Build the independent static library:

```sh
python3 src/ports/qt6/build_aurora.py --sdk "$SDK" --qt-build "$QT_BUILD" \
  --host-qt "$HOST_QT_683" --binutils "$TARGET_TOOLS" \
  --output "$NEW_OUT/libXosAurora.a"
```

Link it in the archive group with the same Qt Widgets/Gui/Core build and SDK.
The library includes its original wallpaper resource. `build_widgets_fixture.py`
provides the full XOS ELF recipe and emits all commands and hashes. The independent
`aurora_showcase.cpp` consumer demonstrates ordinary Widgets without editor code.

The wallpaper is generated for this task; source, conversion and hashes are in
`assets/provenance.json`. Code is Apache-2.0. Qt/dependency/font notices remain in
`../licenses/`; complete static-distribution/member/relink review is NOT_RUN.

This is cached low-frequency blur, color absorption, highlights, shadows and
application-local alpha composition. It does not implement Apple's Liquid Glass,
real-time refraction, cross-application sampling, 3D acceleration or multi-window
composition. Geometry and premeasurement targets: `docs/design/aurora_glass.md`.
