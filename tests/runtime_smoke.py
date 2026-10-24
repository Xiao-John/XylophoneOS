# SPDX-License-Identifier: Apache-2.0
"""E08-2 real libc files, heap, own children, stdio, pipe EOF and recovery."""
import json
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
from make_work_disk import create_fat32
from work_disk import transfer
from e08_storage_smoke import boot
from process_smoke import resources,command
from task_smoke import send_bytes

def main():
    manifest=json.loads((ROOT/'build/manifest.json').read_text())
    report={'build_id':manifest['build_id'],'checks':[],'status':'failed'}
    guest=None
    try:
        with tempfile.TemporaryDirectory(prefix='xos_runtime_') as folder:
            root=Path(folder);disk=root/'test.img';create_fat32(disk,512)
            for name in ('/bin','/src','/out','/tmp'):
                transfer(disk,'mkdir',name)
            transfer(disk,'import','/bin/runtime_probe.elf',ROOT/'build/user_runtime_probe.image.elf')
            source=root/'input.c';source.write_bytes(b'int source_is_preserved = 42;\n')
            transfer(disk,'import','/src/input.c',source)
            guest=boot(disk,'runtime_smoke')
            baseline=resources(guest)
            for iteration in range(3):
                output=command(guest,'exec-driver /bin/runtime_probe.elf driver',b'kind=exited code=',timeout=45)
                if b'kind=exited code=0' not in output or b'[runtime] files=ok heap=8m args_env_cwd=ok spawn_wait=ok pipe=ok source=preserved' not in output:
                    raise AssertionError(output[-2000:])
                if resources(guest)!=baseline:raise AssertionError('runtime/child/heap resource leak')
                report['checks'].append(f'real_driver_files_heap_env_spawn_pipe_redirect_reclaim_{iteration}')
            # The same executable without explicit creation authority must fail
            # child creation, rather than inherit supervisor/builder access.
            output=command(guest,'exec-file /bin/runtime_probe.elf driver',b'kind=exited code=',timeout=30)
            if b'kind=exited code=0' in output or b'FAILED spawn-copy/wait' not in output:
                raise AssertionError('ordinary program inherited builder authority')
            if resources(guest)!=baseline:raise AssertionError('denied spawn leaked resources')
            report['checks'].append('default_spawn_authority_denied_without_resource_leak')
            command(guest,'sync',b'[files] sync=ok')
            guest.close();guest=None
            output=root/'original.c';transfer(disk,'export','/src/input.c',output)
            if output.read_bytes()!=source.read_bytes():raise AssertionError('source data changed')
            output=root/'object.bin';transfer(disk,'export','/out/object.bin',output)
            if output.read_bytes()!=source.read_bytes():raise AssertionError('child output differs')
            output=root/'redirect.txt';transfer(disk,'export','/out/redirect.txt',output)
            if output.read_bytes()!=b'child-pipe-data\n':raise AssertionError('stdout redirection missing')
            report['checks'].append('disk_export_confirms_source_child_output_and_stdout_redirect')
            report['status']='passed'
            print(f"PASS: {len(report['checks'])} E08-2 groups | build {manifest['build_id']}")
    except Exception as error:
        report['error']=str(error);raise
    finally:
        if guest:guest.close()
        (ROOT/'build/runtime_smoke_report.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
