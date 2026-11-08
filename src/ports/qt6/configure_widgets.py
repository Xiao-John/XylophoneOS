#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Configure the independent XOS Qt Widgets profile; E15/E16 entry points are unchanged."""
import argparse
import os
from pathlib import Path
import re
import subprocess
p = argparse.ArgumentParser(description=__doc__)
for name in ('source', 'build', 'sdk', 'binutils', 'host-qt'):
    p.add_argument('--'+name, type=Path, required=True)
a = p.parse_args()
here = Path(__file__).resolve().parent
source = a.source.resolve()
build = a.build.resolve()

# A quoted -D value in GCC's response file is parsed as the end of the file by
# this Windows cross compiler. The only use is QGuiApplication's default QPA;
# select XOS with a target-specific source literal instead.
gui_cmake = source/'src/gui/CMakeLists.txt'
gui_text = gui_cmake.read_text()
platform_define = '        QT_QPA_DEFAULT_PLATFORM_NAME="${QT_QPA_DEFAULT_PLATFORM}"\n'
if platform_define in gui_text:
    gui_cmake.write_text(gui_text.replace(platform_define, '', 1))
elif 'QT_QPA_DEFAULT_PLATFORM_NAME="${QT_QPA_DEFAULT_PLATFORM}"' in gui_text:
    raise SystemExit('Unexpected Qt QPA definition formatting')

qguiapplication = source/'src/gui/kernel/qguiapplication.cpp'
qgui_text = qguiapplication.read_text()
updated_qgui_text = qgui_text.replace(
    '#ifdef QT_QPA_DEFAULT_PLATFORM_NAME\n        return QStringLiteral(QT_QPA_DEFAULT_PLATFORM_NAME);\n#else',
    '#ifdef __XOS__\n        return QStringLiteral("xos");\n#elif defined(QT_QPA_DEFAULT_PLATFORM_NAME)\n        return QStringLiteral(QT_QPA_DEFAULT_PLATFORM_NAME);\n#else', 1)
updated_qgui_text = updated_qgui_text.replace(
    '#ifdef QT_QPA_DEFAULT_PLATFORM_NAME\n    platformName = QT_QPA_DEFAULT_PLATFORM_NAME;\n#endif',
    '#ifdef __XOS__\n    platformName = "xos";\n#elif defined(QT_QPA_DEFAULT_PLATFORM_NAME)\n    platformName = QT_QPA_DEFAULT_PLATFORM_NAME;\n#endif', 1)
if updated_qgui_text != qgui_text:
    qguiapplication.write_text(updated_qgui_text)

off = '''testlib concurrent xml network sql dbus icu stack_protector intelcet
stack_clash_protection poll_select poll_poll poll_ppoll poll_pollts process
processenvironment filesystemwatcher sharedmemory systemsemaphore futimens
memmem memrchr library dlopen filedialog opengl egl eglfs xcb xcb_xlib vulkan
fontconfig system_freetype system_harfbuzz png jpeg gif pdf sessionmanager
cups evdev libinput tslib linuxfb vnc directfb integrityfb vkkhrdisplay'''.split()
cmd = ['cmake', '-S', str(a.source.resolve()), '-B', str(a.build.resolve()), '-G', 'Ninja',
       '-DCMAKE_TOOLCHAIN_FILE='+str(here/'xos_toolchain.cmake'),
       '-DCMAKE_SUPPRESS_REGENERATION=ON',
       '-DXOS_SDK='+str(a.sdk.resolve()), '-DXOS_BINUTILS_DIR='+str(a.binutils.resolve()),
       '-DQT_QMAKE_TARGET_MKSPEC=xos-g++', '-DQT_HOST_PATH='+str(a.host_qt.resolve()),
       '-DBUILD_SHARED_LIBS=OFF', '-DQT_BUILD_EXAMPLES=OFF', '-DQT_BUILD_TESTS=OFF',
       '-DFEATURE_widgets=ON', '-DFEATURE_gui=ON', '-DFEATURE_freetype=ON', '-DFEATURE_harfbuzz=ON',
       '-DINPUT_freetype=qt', '-DINPUT_harfbuzz=qt', '-DINPUT_opengl=no',
       '-DQT_QPA_DEFAULT_PLATFORM=xos']
cmd += ['-DFEATURE_'+f+'=OFF' for f in off]
subprocess.run(cmd, check=True)

# Qt's generated Windows GCC commands use response files, preserving quoted
# macro values without passing them through cmd.exe's quote parser.
ninja_file = a.build.resolve()/'build.ninja'
ninja_text = ninja_file.read_text()
# GCC emits MSYS /c/... paths in depfiles, which native Windows Ninja cannot
# stat. Disable depfile loading in both generated Ninja files; explicit source
# dependencies remain in build.ninja and output mtimes drive incremental builds.
for generated_ninja in (ninja_file, build/'CMakeFiles'/'rules.ninja'):
    ninja_text = generated_ninja.read_text()
    ninja_text = re.sub(r'^  (?:depfile = \$DEP_FILE|deps = gcc)\r?\n', '',
                        ninja_text, flags=re.M)
    generated_ninja.write_text(ninja_text)
(a.build.resolve()/'.ninja_deps').unlink(missing_ok=True)

# Qt's synced forwarding headers embed absolute Windows paths. The target GCC
# treats those as relative include names, so make paths inside this build
# relocatable before compilation starts.
include_root = build/'include'
include_line = re.compile(r'^(#include\s+")([^"]+)(".*)$', re.M)
for header in include_root.rglob('*'):
    if not header.is_file():
        continue
    try:
        contents = header.read_text()
    except (UnicodeError, OSError):
        continue

    def relative_include(match):
        target_text = match.group(2).replace('/', os.sep).replace('\\', os.sep)
        target = Path(target_text)
        for root in (source, build):
            try:
                target = target.resolve().relative_to(root)
            except ValueError:
                continue
            resolved = (root/target).resolve()
            if not resolved.is_file():
                raise SystemExit('Qt forwarded header target missing: '+str(resolved))
            relative = Path(os.path.relpath(resolved, header.parent)).as_posix()
            return match.group(1)+relative+match.group(3)
        return match.group(0)

    updated = include_line.sub(relative_include, contents)
    if updated != contents:
        header.write_text(updated)
