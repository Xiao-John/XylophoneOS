#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Create a binding only when stripping the symbol ELF reproduces the running ELF."""
import argparse,hashlib,json,subprocess,tempfile
from pathlib import Path
from fb2_symbolize import read_bounded,Invalid

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('running',type=Path);p.add_argument('symbols',type=Path);p.add_argument('output',type=Path);p.add_argument('--objcopy',default='x86_64-elf-objcopy');a=p.parse_args()
 try:
  run=read_bounded(a.running,64*1024*1024);sym=read_bounded(a.symbols,64*1024*1024)
  with tempfile.TemporaryDirectory(prefix='xos_fb2_binding_') as d:
   source=Path(d)/'source.elf';result=Path(d)/'stripped.elf';source.write_bytes(sym)
   subprocess.run([a.objcopy,'--strip-debug',str(source),str(result)],check=True,timeout=30)
   if result.read_bytes()!=run:raise Invalid('stripped symbols do not match running ELF')
  receipt={'version':1,'running_sha256':hashlib.sha256(run).hexdigest(),'symbols_sha256':hashlib.sha256(sym).hexdigest()}
  with a.output.open('x',encoding='utf8') as out:json.dump(receipt,out,sort_keys=True);out.write('\n')
 except (OSError,Invalid,subprocess.SubprocessError) as e:p.exit(1,'fb2-bind: '+str(e)+'\n')
if __name__=='__main__':main()
