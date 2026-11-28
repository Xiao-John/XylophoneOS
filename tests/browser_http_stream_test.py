# SPDX-License-Identifier: Apache-2.0
"""Host-only streaming HTTP framing regression with sanitizers."""
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
out = root / 'build/browser_http_stream_host'
out.mkdir(parents=True, exist_ok=True)
link_gc = '-Wl,-dead_strip' if sys.platform == 'darwin' else '-Wl,--gc-sections'
cmd = [os.environ.get('CXX', 'clang++'), '-std=c++17', '-Wall', '-Wextra', '-Werror',
       '-Wconversion', '-Wshadow', '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
       '-ffunction-sections', '-fdata-sections', '-O1', '-g',
       '-I' + str(root / 'src/shared/include'), '-I' + str(root / 'src/user/include'),
       str(root / 'tests/browser_http/stream.cpp'), str(root / 'src/ports/browser_http/http.cpp'),
       str(root / 'src/ports/browser_http/transport.cpp'), link_gc, '-o', str(out / 'probe')]
subprocess.run(cmd, check=True)
subprocess.run([str(out / 'probe')], check=True)
print('PASS: streamed HTTP framing (host only)')
