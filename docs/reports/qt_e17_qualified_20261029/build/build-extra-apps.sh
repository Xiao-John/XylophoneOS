#!/bin/zsh
set -eu
args=(--sdk build/qt_e17/sdk --qt-build build/qt_e17/widgets --qt-source build/qt_e17/qtbase --core-build build/qt_e17/widgets --host-qt /Users/perry_guo/Documents/ChatGPT/os/XylophoneOS-qt6-e15/build/qt_e15/host-install --binutils .cache/xos_seed/threading_sdk_tools)
python3 src/ports/qt6/build_widgets_fixture.py --source tests/fixtures/qt6/gui_demo.cpp "${args[@]}" --output build/qt_e17/final_gui/qt_demo.elf > build/qt_e17/final-gui-build.log 2>&1
python3 src/ports/qt6/build_widgets_fixture.py --source tests/fixtures/qt6/widgets_resources.cpp "${args[@]}" --output build/qt_e17/final_resources/widgets_resources.elf > build/qt_e17/final-resources-build.log 2>&1
python3 src/ports/qt6/build_widgets_fixture.py --source tests/fixtures/qt6/wake_gate_probe.cpp "${args[@]}" --output build/qt_e17/final_wake/wake_gate_probe.elf > build/qt_e17/final-wake-build.log 2>&1
python3 src/ports/qt6/build_widgets_fixture.py --source tests/fixtures/qt6/save_failures.cpp "${args[@]}" --wrap _ZN3xos4file6Client5closeEj --wrap _ZN3xos4file6Client4syncEv --wrap _ZN3xos4file6Client13chunk_replaceEjPKvj --wrap _ZN3xos4file6Client14commit_replaceEv --output build/qt_e17/final_save/save_failures.elf > build/qt_e17/final-save-build.log 2>&1
