#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Audit this userland-only task against its explicit immutable system baseline."""
import argparse,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--base',default='3377dbf35bdb43d850c9a2b8e8076da3be146f3d')
p.add_argument('--output',type=Path,required=True);a=p.parse_args()
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).splitlines()
changed=set(git('diff','--name-only',a.base,'--'))|set(git('ls-files','--others','--exclude-standard'))
protected=('src/kernel/','src/shared/','src/user/libc/','src/user/include/','src/ports/qt6/qpa/')
violations=sorted(name for name in changed if name.startswith(protected))
report={'status':'PASSED' if not violations else 'FAILED','base':a.base,
        'kernel_source_changes':sorted(n for n in changed if n.startswith('src/kernel/')),
        'system_abi_and_runtime_changes':violations,'scope':'system sources/ABI; new opt-in Aurora userspace APIs are intentional',
        'violations':violations}
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2));raise SystemExit(bool(violations))
