#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
set -eu

qemu-system-x86_64 --version
qemu-system-x86_64 -audiodev help 2>&1 | tee /out/audio-drivers.txt
qemu-system-x86_64 -machine pc-i440fx-10.0,help 2>&1 | tee /out/machine-help.txt
grep -i -E 'pcspk|audiodev' /out/machine-help.txt || true

nasm -f bin /probe/pcspk_boot.asm -o /out/pcspk_boot.bin
python3 - <<'PY'
from pathlib import Path
image = bytearray(1474560)
image[:512] = Path('/out/pcspk_boot.bin').read_bytes()
Path('/out/pcspk.img').write_bytes(image)
PY

python3 - <<'PY'
import subprocess, time
cmd = [
    'qemu-system-x86_64', '-machine', 'pc-i440fx-10.0,pcspk-audiodev=audio0',
    '-accel', 'tcg', '-smp', '1', '-nic', 'none', '-vga', 'none', '-S',
    '-drive', 'file=/out/pcspk.img,format=raw,if=floppy,readonly=on',
    '-boot', 'order=a,strict=on', '-no-reboot', '-no-shutdown',
    '-serial', 'none', '-monitor', 'stdio', '-display', 'none',
    '-audiodev', 'wav,id=audio0,path=/out/pcspk-raw.wav',
]
p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                     stderr=subprocess.PIPE, text=True)
if p.poll() is None:
    p.stdin.write('cont\n')
    p.stdin.flush()
    time.sleep(2.5)
    p.stdin.write('quit\n')
    p.stdin.flush()
try:
    p.wait(timeout=10)
except subprocess.TimeoutExpired:
    p.terminate()
    p.wait(timeout=5)
print('qemu_exit=', p.returncode)
if p.returncode != 0:
    print(p.stderr.read())
    raise SystemExit(p.returncode or 1)
PY

python3 - <<'PY'
import json, math, struct
raw_path = '/out/pcspk-raw.wav'
path = '/out/pcspk.wav'
with open(raw_path, 'rb') as f:
    raw_capture = bytearray(f.read())
if len(raw_capture) < 44 or raw_capture[0:4] != b'RIFF' or raw_capture[8:12] != b'WAVE' or raw_capture[36:40] != b'data':
    raise SystemExit('unexpected raw WAV capture')
print('qemu_raw_header_hex=', bytes(raw_capture[:44]).hex())
# QEMU 11.1.x's WAV backend leaves RIFF/data lengths at zero after quit.
# Preserve the raw file and create a normalized copy with lengths derived only
# from its actual, closed file size.
struct.pack_into('<I', raw_capture, 4, len(raw_capture) - 8)
struct.pack_into('<I', raw_capture, 40, len(raw_capture) - 44)
with open(path, 'wb') as f:
    f.write(raw_capture)
with open(path, 'rb') as f:
    header = f.read(44)
print('normalized_wav_header_hex=', header.hex())
if header[0:4] != b'RIFF' or header[8:12] != b'WAVE' or header[36:40] != b'data':
    raise SystemExit('unexpected WAV header')
if struct.unpack_from('<I', header, 4)[0] != len(raw_capture)-8 or struct.unpack_from('<I', header, 40)[0] != len(raw_capture)-44:
    raise SystemExit('WAV length fields do not match capture size')
channels, rate, bits = struct.unpack_from('<HI', header, 22)[0], struct.unpack_from('<I', header, 24)[0], struct.unpack_from('<H', header, 34)[0]
width = bits // 8
raw = bytes(raw_capture[44:])
frames = len(raw) // (channels * width)
if width != 2:
    raise SystemExit('unexpected WAV sample width: %d' % width)
samples = struct.unpack('<%dh' % (len(raw)//2), raw)
# Use the first channel for a sequence of 100 ms RMS windows.
mono = samples[::channels]
window = max(1, rate // 10)
levels = []
for start in range(0, len(mono), window):
    part = mono[start:start+window]
    if not part: continue
    rms = math.sqrt(sum(x*x for x in part)/len(part))
    levels.append({'start_ms': round(start*1000/rate), 'rms': round(rms, 2)})
active = [x for x in levels if x['rms'] > 100]
crossings = sum((left < 0) != (right < 0) for left, right in zip(mono, mono[1:]))
estimated_hz = crossings / (2 * (frames / rate)) if frames else 0
result = {'wav': path, 'channels': channels, 'sample_width_bytes': width,
          'sample_rate_hz': rate, 'frames': frames, 'duration_s': round(frames/rate, 3),
          'zero_crossing_frequency_hz': round(estimated_hz, 2),
          'window_rms_100ms': levels, 'active_windows': active,
          'capture_ends_with_tone': bool(levels and levels[-1]['rms'] > 100)}
print(json.dumps(result, indent=2))
if not active:
    raise SystemExit('no PC speaker signal captured')
if not 4500 <= estimated_hz <= 5500:
    raise SystemExit('captured frequency outside expected range')
PY
