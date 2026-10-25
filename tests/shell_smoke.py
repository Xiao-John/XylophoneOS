# SPDX-License-Identifier: Apache-2.0
"""Guest-only dash A acceptance; a host sh supplies reference script results."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts'),str(ROOT/'tests')]
from boot_smoke import Guest
from task_smoke import send_bytes, pump
from process_smoke import command, resources
from make_work_disk import create_fat32

PROBE = r'''/* SPDX-License-Identifier: Apache-2.0 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(int argc, char **argv) {
    if (argc > 1 && !strcmp(argv[1], "status")) return 17;
    for (int i = 1; i < argc; ++i) printf("arg%d=%d:<%s>\n", i, (int)strlen(argv[i]), argv[i]);
    const char *v = getenv("XOS_SHELL_TEST");
    printf("env=<%s>\n", v ? v : "unset");
    return 0;
}
'''
CASES = {
    'quotes': "v='two words'; printf '<%s>\\n' \"$v\" '' a\"b c\"d 'literal $v'",
    'control': "for v in one two; do if test \"$v\" = one; then printf 'ONE\\n'; else printf 'TWO\\n'; fi; done; false && printf BAD; true || printf BAD; printf 'OK\\n'",
    'while': "n=0; while test $n -lt 3; do printf '%s\\n' $n; n=$((n+1)); done",
    'external': "XOS_SHELL_TEST='export value'; export XOS_SHELL_TEST; $PROBE 'two words' ''; printf 'status=%s\\n' $?",
    'temporary_env': "XOS_SHELL_TEST=temporary $PROBE x; $PROBE y",
    'child_status': "$PROBE status; printf 'child=%s\\n' $?; printf AFTER",
    'cwd': "cd /tmp && pwd; cd / && pwd",
    'missing': "missing_xos_shell_command; printf 'missing=%s\\n' $?",
    'positionals': "set -- 'one two' ''; printf 'n=%s\\n' $#; printf '<%s>\\n' \"$@\"; shift; printf 'n=%s\\n' $#",
}
REJECT = {
    'pipe': 'printf SHOULD_NOT_RUN | printf BAD',
    'subshell': '(printf SHOULD_NOT_RUN)',
    'substitution': 'printf SHOULD_NOT_RUN "$(printf BAD)"',
    'background': 'printf SHOULD_NOT_RUN &',
}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--system',type=Path,default=ROOT/'build/releases/0.0.1-1024')
    a=p.parse_args();manifest=json.loads(a.manifest.read_text())
    elf=ROOT/manifest['elf']
    assert hashlib.sha256(elf.read_bytes()).hexdigest()==manifest['sha256']
    system_manifest = a.system/'manifest.json'
    if not system_manifest.exists(): system_manifest = a.system/'system_manifest.json'
    system = json.loads(system_manifest.read_text())
    assert hashlib.sha256((a.system/'xos.img').read_bytes()).hexdigest()==system['artifacts']['xos.img']['sha256']
    report={'status':'failed','dash_sha256':manifest['sha256'],'system_build_id':system['build_id'],'checks':[]}
    guest=None
    try:
        with tempfile.TemporaryDirectory(prefix='xos_dash_a_') as temp:
            folder=Path(temp);disk=folder/'work.img';create_fat32(disk,512)
            from work_disk import host_tool
            helper=host_tool()
            def transfer(op,path,source=None):
                args=[str(helper),str(disk),op,path]
                if source is not None:args.append(str(source))
                subprocess.run(args,check=True,stdout=subprocess.DEVNULL)
            for directory in ('/usr','/usr/bin','/tests','/tmp'):transfer('mkdir',directory)
            transfer('import','/usr/bin/dash',elf)
            source=folder/'probe.c';source.write_text(PROBE)
            probe=folder/'probe.elf';host=folder/'probe_host'
            from dash_b2_smoke import build_probe
            build_probe(source, probe, a.system/'sdk')
            subprocess.run(['clang',str(source),'-o',str(host)],check=True)
            transfer('import','/usr/bin/probe',probe)
            expected={}
            for name,body in {**CASES,**REJECT}.items():
                script=folder/(name+'.sh')
                script.write_text('PATH=/usr/bin:/bin; PROBE=/usr/bin/probe; export PROBE\n'+body+'\n')
                transfer('import','/tests/'+script.name,script)
                if name in CASES:
                    reference=subprocess.run(['/bin/sh','-c',body],env={'PROBE':str(host),'PATH':'/usr/bin:/bin'},capture_output=True)
                    expected[name]=reference.stdout
            guest=Guest(a.system/'xos.img','dash_a',work_disk=disk)
            guest.expect(b'xos64> ',timeout=40);send_bytes(guest,b'run\r')
            guest.expect_supervisor(trace=True,timeout=40);pump(guest,1.5)
            baseline=resources(guest)
            for name in CASES:
                result=command(guest,'exec-driver /usr/bin/dash /tests/'+name+'.sh',b'kind=exited code=0',timeout=40)
                wanted=expected[name]
                if name in ('external','temporary_env','child_status'):
                    # Kernel lifecycle diagnostics may be interleaved with child stdout.
                    for line in wanted.splitlines():assert line in result,(name,line,result[-2500:])
                else:assert wanted in result,(name,wanted,result[-2500:])
                assert resources(guest)==baseline,name+' leaked resources'
                report['checks'].append(name)
            for name in REJECT:
                result=command(guest,'exec-driver /usr/bin/dash /tests/'+name+'.sh',b'kind=exited code=2',timeout=30)
                assert b'SHOULD_NOT_RUN' not in result and (b'unavailable in XOS dash' in result or b'C1 pipeline requires external commands' in result)
                assert resources(guest)==baseline
                report['checks'].append('reject_'+name)
            command(guest,'exec-driver /usr/bin/dash -c true',b'kind=exited code=0',timeout=30)
            report['checks'].append('command_string')
            start=len(guest.output);send_bytes(guest,b'exec-driver /usr/bin/dash -i\r')
            guest.expect(b'$ ',start=start,timeout=30)
            mark=len(guest.output);send_bytes(guest,b"v='hello dash'; printf '<%s>\\n' \"$v\"\r")
            guest.expect(b'<hello dash>',start=mark,timeout=20);guest.expect(b'$ ',start=mark,timeout=20)
            command(guest,'exit',b'kind=exited code=0',timeout=30)
            assert resources(guest)==baseline
            report['checks'].append('interactive_returns_to_xshell')
            report['status']='passed'
    except Exception as error:
        report['error']=str(error);raise
    finally:
        if guest:guest.close()
        (a.manifest.parent/'shell_smoke_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__':main()
