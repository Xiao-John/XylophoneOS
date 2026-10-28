#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Configure the separate XOS raster QtGui profile; preserves the E15 entry point."""
import argparse
from pathlib import Path
import subprocess
p = argparse.ArgumentParser(description=__doc__)
for name in ('source', 'build', 'sdk', 'binutils', 'host-qt'):
    p.add_argument('--'+name, type=Path, required=True)
a = p.parse_args()
here = Path(__file__).resolve().parent
off = '''testlib concurrent xml network sql dbus icu stack_protector intelcet
stack_clash_protection poll_select poll_poll poll_ppoll poll_pollts process
processenvironment filesystemwatcher sharedmemory systemsemaphore futimens
memmem memrchr library dlopen widgets opengl egl eglfs xcb xcb_xlib vulkan
fontconfig system_freetype system_harfbuzz png jpeg gif pdf sessionmanager
cups evdev libinput tslib linuxfb vnc directfb integrityfb vkkhrdisplay'''.split()
cmd = ['cmake', '-S', str(a.source.resolve()), '-B', str(a.build.resolve()), '-G', 'Ninja',
       '-DCMAKE_TOOLCHAIN_FILE='+str(here/'xos_toolchain.cmake'),
       '-DXOS_SDK='+str(a.sdk.resolve()), '-DXOS_BINUTILS_DIR='+str(a.binutils.resolve()),
       '-DQT_QMAKE_TARGET_MKSPEC=xos-g++', '-DQT_HOST_PATH='+str(a.host_qt.resolve()),
       '-DBUILD_SHARED_LIBS=OFF', '-DQT_BUILD_EXAMPLES=OFF', '-DQT_BUILD_TESTS=OFF',
       '-DFEATURE_gui=ON', '-DFEATURE_freetype=ON', '-DFEATURE_harfbuzz=ON',
       '-DINPUT_freetype=qt', '-DINPUT_harfbuzz=qt', '-DINPUT_opengl=no',
       '-DQT_QPA_DEFAULT_PLATFORM=xos']
cmd += ['-DFEATURE_'+f+'=OFF' for f in off]
subprocess.run(cmd, check=True)
