#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Configure an experimental static QtCore build; no gate is implied."""
import argparse
from pathlib import Path
import subprocess

here = Path(__file__).resolve().parent
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--source', type=Path, required=True)
p.add_argument('--build', type=Path, required=True)
p.add_argument('--sdk', type=Path, required=True)
p.add_argument('--binutils', type=Path, required=True)
p.add_argument('--host-qt', type=Path, required=True)
a = p.parse_args()
features_off = ['testlib', 'concurrent', 'xml', 'gui', 'network', 'sql', 'dbus', 'icu', 'stack_protector', 'intelcet',
                'stack_clash_protection', 'poll_select', 'poll_poll', 'poll_ppoll', 'poll_pollts',
                'process', 'processenvironment', 'filesystemwatcher', 'sharedmemory',
                'systemsemaphore', 'futimens', 'memmem', 'memrchr', 'library', 'dlopen']
cmd = ['cmake', '-S', str(a.source.resolve()), '-B', str(a.build.resolve()), '-G', 'Ninja',
       '-DCMAKE_TOOLCHAIN_FILE=' + str(here / 'xos_toolchain.cmake'),
       '-DXOS_SDK=' + str(a.sdk.resolve()), '-DXOS_BINUTILS_DIR=' + str(a.binutils.resolve()),
       '-DQT_QMAKE_TARGET_MKSPEC=xos-g++', '-DQT_HOST_PATH=' + str(a.host_qt.resolve()),
       '-DBUILD_SHARED_LIBS=OFF', '-DQT_BUILD_EXAMPLES=OFF', '-DQT_BUILD_TESTS=OFF']
cmd += ['-DFEATURE_' + feature + '=OFF' for feature in features_off]
subprocess.run(cmd, check=True)
