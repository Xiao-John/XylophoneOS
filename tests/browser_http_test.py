# SPDX-License-Identifier: Apache-2.0
"""Build/run the pure parser on the host; this is explicitly not a network gate."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, default=ROOT/'build/browser_http_host')
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    sources = [ROOT/'src/ports/browser_http/http.cpp', ROOT/'tests/browser_http/probe.cpp']
    command = [os.environ.get('CXX', 'clang++'), '-std=c++17', '-Wall', '-Wextra', '-Werror',
               '-Wconversion', '-Wshadow', '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
               '-O1', '-g', *map(str,sources), '-o', str(args.output/'probe')]
    built = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (args.output/'build.log').write_text(built.stdout)
    if built.returncode:
        print(built.stdout)
        raise SystemExit(built.returncode)
    run = subprocess.run([str(args.output/'probe')], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (args.output/'run.log').write_text(run.stdout)
    (args.output/'report.json').write_text(json.dumps({
        'status': 'PASSED' if run.returncode==0 else 'FAILED', 'evidence_kind':'host_parser_only',
        'network': 'NOT_RUN', 'command':command, 'returncode':run.returncode,
        'source_sha256':{str(s.relative_to(ROOT)):hashlib.sha256(s.read_bytes()).hexdigest() for s in sources},
        'compiler':subprocess.check_output([command[0],'--version'],text=True).splitlines()[0],
        'output':run.stdout,
    },indent=2)+'\n')
    print(run.stdout,end='')
    raise SystemExit(run.returncode)

if __name__=='__main__':
    main()
