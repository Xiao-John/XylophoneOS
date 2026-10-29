#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check FB2 report validation and exact ELF binding against a real built fault."""
import hashlib,json,os,re,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from fb2_symbolize import validate,symbolize,Invalid

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v),encoding='utf8')
def main():
    system=Path(os.environ.get('FB12_SYSTEM',ROOT/'build/fb12/system'))
    acceptance=Path(os.environ.get('FB12_ACCEPTANCE',ROOT/'build/fb12/acceptance'))
    run=system/'user_fault.image.elf';sym=system/'user_fault.elf'
    source=json.loads((acceptance/'report.json').read_text())
    item=next(x for x in source['checks'] if x['name']=='guest_fault_bundle_and_bound_symbol')
    assert sha(run)==item['run_sha256']
    matches=re.findall(rb'event=fault pid=\d+ vector=14 rip=0x([0-9a-f]+) cr2=0x0000000000100000', (acceptance/'first.serial.log').read_bytes());assert matches
    address=int(matches[-1],16)
    rid='12'*16
    with tempfile.TemporaryDirectory(prefix='xos_fb2_') as d:
        root=Path(d);report=root/'report';report.mkdir();receipt=root/'binding.json'
        write(report/'report.json',{'version':1,'run_id':rid,'status_version':1,'outcome':'faulted','pid':'000000000000000c','code':'0','vector':14,'address':'0000000000100000','instruction':f'{address:016x}'})
        write(report/'image.json',{'version':1,'run_id':rid,'source':'file','size':run.stat().st_size,'sha256':sha(run),'elf_type':'ET_EXEC','sdk_profile':None,'build_id':None})
        write(report/'context.json',{'version':1,'run_id':rid,'collector_version':'fb2-test','system_build_id':None,'monotonic_ns':None,'utc_ns':None})
        def manifest():
            files={name:{'size':(report/name).stat().st_size,'sha256':sha(report/name)} for name in ('report.json','image.json','context.json')}
            write(report/'manifest.json',{'version':1,'run_id':rid,'state':'complete','files':files})
        manifest();write(receipt,{'version':1,'running_sha256':sha(run),'symbols_sha256':sha(sym)})
        result=symbolize(report,run,sym,receipt,'x86_64-elf-addr2line');assert result['location']!='??:0';print('symbol:',result['location'])
        def rejects(fn):
            try:fn()
            except (Invalid,ValueError,UnicodeError,OSError):return
            raise AssertionError('invalid input accepted')
        write(receipt,{'version':1,'running_sha256':sha(run),'symbols_sha256':'00'*32});rejects(lambda:symbolize(report,run,sym,receipt,'x86_64-elf-addr2line'))
        content=(report/'report.json').read_bytes();(report/'report.json').write_bytes(content+b' ');rejects(lambda:validate(report));(report/'report.json').write_bytes(content)
        (report/'extra').write_text('x');rejects(lambda:validate(report));(report/'extra').unlink()
        (report/'report.json').write_text('{"version":1,"version":1}');manifest();rejects(lambda:validate(report))
        (report/'report.json').write_bytes(content);manifest()
        original=json.loads(content);original['instruction']='ffffffffffffffff';write(report/'report.json',original);manifest()
        write(receipt,{'version':1,'running_sha256':sha(run),'symbols_sha256':sha(sym)});rejects(lambda:symbolize(report,run,sym,receipt,'x86_64-elf-addr2line'))
        (report/'report.json').write_bytes(content);manifest()
        wrong=system/'user_hello.elf';write(receipt,{'version':1,'running_sha256':sha(run),'symbols_sha256':sha(wrong)});rejects(lambda:symbolize(report,run,wrong,receipt,'x86_64-elf-addr2line'))
        image_content=(report/'image.json').read_bytes()
        (report/'image.json').unlink();(report/'image.json').symlink_to(ROOT/'build/manifest.json');rejects(lambda:validate(report))
        (report/'image.json').unlink();(report/'image.json').write_bytes(image_content)
        (report/'report.json').write_bytes(b'\xff');manifest();rejects(lambda:validate(report))
        (report/'report.json').write_bytes(b' '*8193);rejects(lambda:validate(report))
        original=json.loads(content);original['extra']='unexpected';write(report/'report.json',original);manifest();rejects(lambda:validate(report))
        (report/'report.json').write_bytes(content);manifest()
        rejects(lambda:symbolize(report,run,ROOT/'does-not-exist.elf',receipt,'x86_64-elf-addr2line'))
        print('PASS matched symbols; reject wrong/missing symbols, tampering, extra/duplicate fields, invalid address/UTF-8, forged binding, symlink and oversize')
if __name__=='__main__':main()
