#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Production navigation policy regressions; no Qt or guest qualification."""
import os
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
output = root / 'build/browser_network_policy'
output.mkdir(parents=True, exist_ok=True)
command = [os.environ.get('CXX', 'c++'), '-std=c++17', '-Wall', '-Wextra', '-Werror',
           '-Wconversion', '-Wshadow', '-O1', '-g', '-fsanitize=address,undefined',
           '-fno-sanitize-recover=all', '-fno-omit-frame-pointer', '-fno-pie', '-no-pie',
           str(root / 'src/ports/browser_http/http.cpp'),
           str(root / 'tests/browser_http/navigation_policy.cpp'), '-o', str(output / 'probe')]
subprocess.run(command, check=True)
environment = dict(os.environ)
# LeakSanitizer cannot inspect processes under the hosted ptrace environment.
# ASan bounds/use-after-free and UBSan remain enabled; this is not a leak gate.
environment.setdefault('ASAN_OPTIONS', 'detect_leaks=0')
subprocess.run([str(output / 'probe')], check=True, env=environment)
