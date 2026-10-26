# SPDX-License-Identifier: Apache-2.0
"""Re-use hash-recorded accepted userland payloads on the E14 kernel, without rebuilding them."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
from boot_smoke import Guest
from cpython_py1_smoke import install_stage
from make_work_disk import create_fat32
from process_smoke import command,resources
from task_smoke import send_bytes,pump
from work_disk import transfer

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dash',type=Path,required=True);p.add_argument('--make',type=Path,required=True)
    p.add_argument('--python-stage',type=Path,required=True);p.add_argument('--thread-probe',type=Path,required=True)
    args=p.parse_args();build=ROOT/'build';stage=args.python_stage.resolve()
    report={'status':'failed','build_id':json.loads((build/'manifest.json').read_text())['build_id'],
            'input_sha256':{name:sha(path) for name,path in [('dash',args.dash),('make',args.make),('cpp_threads',args.thread_probe)]},'checks':[]}
    guest=None
    try:
        stage_manifest=json.loads((stage.parent/(stage.name+'_manifest.json')).read_text())
        for file in stage_manifest['files']:assert sha(stage/file['path'].lstrip('/'))==file['sha256'],file['path']
        report['python_stage_manifest_sha256']=sha(stage.parent/(stage.name+'_manifest.json'))
        with tempfile.TemporaryDirectory(prefix='xos_e14_compat_') as folder:
            folder=Path(folder);disk=folder/'work.img';create_fat32(disk,512)
            install_stage(disk,stage)
            for directory in ('/work','/out','/bin'):transfer(disk,'mkdir',directory)
            for source,destination in [(args.dash,'/usr/bin/dash'),(args.make,'/usr/bin/make'),(args.thread_probe,'/bin/cppthread')]:
                transfer(disk,'import',destination,source)
            script=folder/'g02.sh';script.write_text('''x=$(printf 'FORK_OK\\n')
printf '%s\\n' "$x"
printf 'PIPE_OK\\n' | /usr/bin/dash -c 'read v; printf "%s\\n" "$v"'
read text <<'DOC'
HEREDOC_OK
DOC
printf '%s\\n' "$text"
''')
            makefile=folder/'Makefile';makefile.write_text('SHELL=/usr/bin/dash\nall:\n\tprintf "MAKE_OK\\n" > /out/e14.txt\n')
            transfer(disk,'import','/work/g02.sh',script);transfer(disk,'import','/work/Makefile',makefile)
            transfer(disk,'import','/work/threading.py',ROOT/'tests/fixtures/cpython_t3_py/threading_core.py')
            guest=Guest(build/'xos-install-dash.iso','display_compat',work_disk=disk,iso=True)
            guest.expect(b'xos64> ');guest.expect(b'payload_bytes=')
            send_bytes(guest,b'run\r');guest.expect_supervisor(trace=True);pump(guest,1.6)
            baseline=resources(guest)
            output=command(guest,'exec-driver /usr/bin/dash /work/g02.sh',b'kind=exited code=',timeout=60)
            assert b'kind=exited code=0' in output and all(marker in output for marker in (b'FORK_OK',b'PIPE_OK',b'HEREDOC_OK')),output[-2000:]
            assert resources(guest)==baseline;report['checks'].append('dash_C1_pipeline_C2_fork_command_substitution_C3_heredoc')
            output=command(guest,'exec-driver /usr/bin/make -B -f /work/Makefile',b'kind=exited code=',timeout=60)
            assert b'kind=exited code=0' in output,output[-2000:]
            output=command(guest,'cat /out/e14.txt',b'MAKE_OK');assert resources(guest)==baseline
            report['checks'].append('make_runs_real_shell_recipe_and_file_content_matches')
            output=command(guest,'python3 /work/threading.py',b'kind=exited code=',timeout=90)
            assert b'T3_PY_CORE_OK Lock RLock Condition Event Queue' in output and b'kind=exited code=0' in output,output[-2000:]
            assert resources(guest)==baseline;report['checks'].append('CPython_real_threads_locks_condition_event_queue')
            output=command(guest,'display-start',b'result=0');service=int(re.search(rb'pid=(\d+) result=0',output)[1]);with_service=resources(guest)
            output=command(guest,'exec-file /bin/cppthread',b'kind=exited code=',timeout=90)
            assert b'[cppthread] thread mutex cond once retry TLS exception guard chrono=ok' in output and b'kind=exited code=0' in output,output[-2000:]
            assert resources(guest)==with_service;report['checks'].append('accepted_Cpp_thread_profile_runs_while_display_service_active')
            command(guest,'exec gfxdemo check',b'checks=pass');assert resources(guest)==with_service
            command(guest,'exec gfxdemo stop',b'kind=exited code=0');command(guest,f'wait {service}',b'kind=exited code=0')
            assert resources(guest)==baseline;report['resource_baseline']=baseline
            report['checks'].append('file_backed_ISO_payload_contract_and_gui_recovery_with_existing_userland')
        report['status']='passed'
    except Exception as error:report['error']=repr(error);raise
    finally:
        if guest:guest.close()
        (build/'display_compat_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS',len(report['checks']),'E14 compatibility groups')
if __name__=='__main__':main()
