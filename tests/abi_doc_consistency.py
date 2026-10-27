# SPDX-License-Identifier: Apache-2.0
"""Check the explicitly current SDK table, excluding historical reports."""
import argparse,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=ROOT/'build/audit_01')
    args=parser.parse_args()
    text=(ROOT/'docs/e04_loader_sdk.md').read_text()
    section=text.split('## 当前ABI速查（0054）',1)[1].split('\n## ',1)[0]
    headers={'process':(ROOT/'src/shared/include/xos/process_abi.hpp').read_text(),
             'file':(ROOT/'src/shared/include/xos/file_abi.hpp').read_text(),
             'display':(ROOT/'src/shared/include/xos/display_abi.hpp').read_text()}
    names=['sys_pipe_wait','sys_process_guard','sys_random_bytes','sys_clock_realtime','sys_display','sys_display_present','clone_session','anonymous','anonymous_seal','maintenance_acquire','maintenance_release','truncate']
    actual={}
    for name in names:
        source=headers['display' if name.startswith('sys_display') else 'process' if name.startswith('sys_') else 'file']
        value=int(re.search(r'\b'+name+r'\s*=\s*(\d+)',source).group(1))
        documented=re.findall(r'\|\s*`'+name+r'`\s*\|\s*(\d+)\s*\|',section)
        assert documented==[str(value)],(name,value,documented)
        actual[name]=value
    assert len({actual[n] for n in names if n.startswith('sys_')})==6
    assert len({actual[n] for n in names if not n.startswith('sys_')})==6
    numbers={}
    for path in (ROOT/'src/shared/include/xos').glob('*abi.hpp'):
        for name,value in re.findall(r'\b(sys_[a-z0-9_]+)\s*=\s*(\d+)',path.read_text()):
            number=int(value)
            assert number not in numbers,(number,numbers.get(number),name)
            numbers[number]=name
    out=args.output_dir;out.mkdir(parents=True,exist_ok=True)
    (out/'abi_doc_report.json').write_text(json.dumps({'status':'passed','current':actual,'historical_reports':'not_modified'},indent=2)+'\n')
    print('PASS current ABI table:',actual)
if __name__=='__main__':main()
