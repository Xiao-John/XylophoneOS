#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Host parser/reader regression; TLS termination is tested only in the guest."""
import argparse
from hashlib import file_digest
import json
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
def digest(path):
    with path.open('rb') as stream:return file_digest(stream,'sha256').hexdigest()
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    sources=[ROOT/name for name in ('src/ports/browser_http/http.cpp','src/ports/browser_http/transport.cpp','tests/browser_http/framing.cpp')]
    inputs=[*sources,ROOT/'src/ports/browser_http/transport.hpp',Path(__file__)]
    compiler=os.environ.get('CXX','clang++')
    command=[compiler,'-std=c++20','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
        '-fno-omit-frame-pointer','-I',str(ROOT/'src/shared/include'),'-I',str(ROOT/'src/user/include'),
        *map(str,sources),'-o',str(out/'framing')]
    report={'status':'failed','scope':'host_reader_only','command':command,
            'inputs':{str(path.relative_to(ROOT)):digest(path) for path in inputs}}
    try:
        with (out/'build.log').open('w') as stream:subprocess.run(command,check=True,stdout=stream,stderr=subprocess.STDOUT)
        with (out/'run.log').open('w') as stream:subprocess.run([out/'framing'],check=True,stdout=stream,stderr=subprocess.STDOUT)
        report['status']='passed'
    finally:
        (out/'report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(report['status'])
if __name__=='__main__':main()
