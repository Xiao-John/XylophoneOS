# Aurora Interactium samples

`interactium_showcase.cpp` opens two independent Qt top-level windows through the
Interactium QPA. The Counter window uses a `QPushButton` to increment its `QLabel` and
has its own close button. The Notes window uses `QLineEdit` and `QPlainTextEdit`; click
`Add note` or press Enter to append text. Each window closes independently. Press Escape
while the Counter window is focused to exit the application. Both use the Aurora desktop
surface and the ordinary Qt Widgets palette/layout system.

Build with matching current Qt Widgets, threading SDK, Qt source, host Qt 6.8.3 tools,
and target binutils:

```sh
python3 src/ports/qt6/build_widgets_fixture.py \
  --source src/ports/qt6/aurora/interactium_showcase.cpp \
  --sdk "$CURRENT_SDK" --qt-build "$QT_BUILD" --core-build "$QT_BUILD" \
  --qt-source "$QT_SOURCE" --host-qt "$HOST_QT_683" \
  --binutils "$TARGET_TOOLS" --output build/aurora_interactium/aurora.elf
```

Import `build/aurora_interactium/aurora.elf` into the target work disk as
`/AURORA.ELF`, boot the matching system image, and run:

```text
run
interactium-start
exec /AURORA.ELF
```

`interactium-start` starts the Display Service and then Interactium; the Display Service
grants its single client slot to Interactium. Do not run `display-start` at the same time.
The QPA maps each native top-level Qt window to an Interactium window ID. Interactium
routes pointer input to the hit window and keyboard input to the focused window.
