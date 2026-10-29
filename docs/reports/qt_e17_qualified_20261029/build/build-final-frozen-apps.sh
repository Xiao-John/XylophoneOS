#!/bin/zsh
set -eu
args=(--sdk build/qt_e17/sdk --qt-build build/qt_e17/widgets --qt-source build/qt_e17/qtbase --core-build build/qt_e17/widgets --host-qt /Users/perry_guo/Documents/ChatGPT/os/XylophoneOS-qt6-e15/build/qt_e15/host-install --binutils .cache/xos_seed/threading_sdk_tools)
python3 src/ports/qt6/build_widgets_fixture.py --source src/ports/qt6/editor/main.cpp "${args[@]}" --output build/qt_e17/final_editor/notes.elf > build/qt_e17/qualified-editor-build.log 2>&1
python3 src/ports/qt6/build_widgets_fixture.py --source tests/fixtures/qt6/widgets_probe.cpp "${args[@]}" --output build/qt_e17/final_probe/widgets_probe.elf > build/qt_e17/qualified-probe-build.log 2>&1
python3 src/ports/qt6/build_widgets_fixture.py --source tests/fixtures/qt6/aurora_showcase.cpp "${args[@]}" --output build/qt_e17/final_showcase/aurora_showcase.elf > build/qt_e17/qualified-showcase-build.log 2>&1
