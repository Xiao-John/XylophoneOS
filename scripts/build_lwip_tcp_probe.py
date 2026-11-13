#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the controlled TCP guest probe and record its exact inputs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from xos_app import tree_receipt

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sdk',type=Path,required=True);p.add_argument('--archive',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    sdk=a.sdk.resolve();archive=a.archive.resolve();out=a.output.resolve()
    if not out.is_relative_to(ROOT/'build'): p.error('output must be inside build')
    out.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy();env.update(XOS_SDK=str(sdk),XOS_SOURCE_ARCHIVE=str(archive),XOS_OUT=str(out/'port'),XOS_SDK_UNREGISTERED_OK='1')
    subprocess.run([sys.executable,str(ROOT/'src/ports/lwip/build.py')],env=env,check=True)
    lib=out/'port/tree/usr/lib/liblwip.a';include=out/'port/tree/usr/share/lwip/include'
    binary=out/'tcp_probe.elf';compiler=shutil.which('x86_64-elf-g++')
    command=[compiler,'-std=c++20','-O2','-g','-ffreestanding','-fno-exceptions','-fno-rtti','-fno-threadsafe-statics',
        '-fno-use-cxa-atexit','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-fno-stack-protector','-fno-pic','-fno-pie','-mno-red-zone','-nostdinc++',
        '-idirafter',str(sdk/'include'),'-I',str(include),str(ROOT/'src/ports/lwip/net_tcp_probe.cpp'),'-nostdlib','-static','-no-pie',
        '-Wl,-z,noexecstack','-T',str(sdk/'user.ld'),str(sdk/'crt0_posix.o'),'-Wl,--start-group',str(lib),str(sdk/'lib/libxos.a'),
        str(sdk/'lib/libxos_loader.a'),str(sdk/'lib/libc.a'),str(sdk/'lib/libm.a'),'-lgcc','-Wl,--end-group','-o',str(binary)]
    subprocess.run(command,check=True)
    receipt={'source_sha256':sha(ROOT/'src/ports/lwip/net_tcp_probe.cpp'),'builder_sha256':sha(Path(__file__)),
      'sdk_tree_sha256':tree_receipt(sdk)[0],'archive_sha256':sha(archive),'lwip_library_sha256':sha(lib),
      'port_receipt_sha256':sha(out/'port/build_receipt.json'),'binary_sha256':sha(binary),'command':command}
    (out/'tcp_probe.receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(binary)
if __name__=='__main__':main()
