#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Hash-check pinned lwIP sources and cross-build a NO_SYS archive; not network qualification."""
import argparse,hashlib,json,os,subprocess,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];PORT=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--sdk',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
a.output.mkdir(parents=True,exist_ok=False)
tools=a.output/'target_tools';tools.mkdir()
for name in ('as','ld'):
 path=shutil.which(os.environ.get('CROSS_PREFIX','x86_64-elf-')+name);assert path
 (tools/name).symlink_to(Path(path).resolve())
os.environ['COMPILER_PATH']=str(tools.resolve())
lock=json.loads((PORT/'source_lock.json').read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for name,digest in lock['files'].items():assert sha(a.source/name)==digest,name
sources=sorted((a.source/'src/core').glob('*.c'))+sorted((a.source/'src/core/ipv4').glob('*.c'))+[a.source/'src/netif/ethernet.c']
cc=os.environ.get('CROSS_PREFIX','x86_64-elf-')+'gcc';ar=os.environ.get('CROSS_PREFIX','x86_64-elf-')+'ar';commands=[];objects=[]
for source in sources:
 obj=a.output/(source.stem+'.o');cmd=[cc,'-std=c11','-O2','-g','-ffreestanding','-fno-pie','-mno-red-zone','-m64','-I'+str(PORT/'include'),'-isystem',str(a.sdk/'include'),'-I'+str(a.source/'src/include'),'-Wall','-Wextra','-Werror','-c',str(source),'-o',str(obj)]
 commands.append(cmd);subprocess.run(cmd,check=True);objects.append(str(obj))
archive=a.output/'liblwip_xos_probe.a';cmd=[ar,'rcs',str(archive),*objects];subprocess.run(cmd,check=True);commands.append(cmd)
(a.output/'receipt.json').write_text(json.dumps({'status':'CROSS_COMPILE_PASSED','network_guest_status':'NOT_RUN','archive_sha256':sha(archive),'source_commit':lock['commit'],'commands':commands,'profile_sha256':sha(PORT/'include/lwipopts.h'),'unresolved_hooks':subprocess.check_output([os.environ.get('CROSS_PREFIX','x86_64-elf-')+'nm','-u',str(archive)],text=True)},indent=2)+'\n')
print('lwIP target archive CROSS_COMPILE_PASSED; guest network NOT_RUN')
