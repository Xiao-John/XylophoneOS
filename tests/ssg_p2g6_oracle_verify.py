#!/usr/bin/env python3
"""Independently compare both completed recover-run baselines with the liteHTML model."""
import hashlib,json,sys
from pathlib import Path
from ssg_browser_structure import decode_capture, validate_oracle, compare_structure
out=Path(sys.argv[1]); report=json.loads((out/'report.json').read_text()); cap=decode_capture((out/'serial.log').read_bytes()); fs=cap['frames']; os=cap['oracles']
def require(x,m):
    if not x: raise AssertionError(m)
require(len(os)==5,'expected before/after A, before interrupted, before/after B')
req=[f for f in fs if f['direction']=='REQ']; resp=[f for f in fs if f['direction']=='RESP']; starts=[i for i,f in enumerate(req) if f['data'].get('op')=='snapshot_begin'];require(len(starts)==3,'unexpected sessions')
receipt=json.loads(Path(report['inputs']['browser']['path']).with_suffix('.receipt.json').read_text()); require(receipt['test_structure_oracle'] is True and receipt['elf_sha256']==report['inputs']['browser']['sha256'],'test build mismatch')
root=Path(__file__).resolve().parents[1]
for name in ('build.py','main.cpp','view.hpp','test_structure_oracle.hpp','content.hpp','scene_geometry.hpp'):
    rel='src/ports/aurora_browser/'+name; matches=[v for k,v in receipt['inputs'].items() if k.endswith('/'+rel)];require(matches==[hashlib.sha256((root/rel).read_bytes()).hexdigest()],'source receipt mismatch '+name)
results=[]
for label,begin,end,ob,oa in [('A',starts[0],starts[1],os[0],os[1]),('B',starts[2],len(req),os[3],os[4])]:
    before,after=ob['data'],oa['data']; reference=validate_oracle(before,report['inputs']['input']['sha256'],'before');validate_oracle(after,report['inputs']['input']['sha256'],'after')
    for k in ('document','inputSha256','sourceInstance','providerPid','sourceEpoch','sourceRevision','nodeCount','structureSha256','nodes'): require(before[k]==after[k],'oracle changed '+k)
    require(req[begin]['end']<=ob['begin']<ob['end']<=resp[begin]['begin'] and req[end-1]['end']<=oa['begin']<oa['end']<=resp[end-1]['begin'],'oracle ordering')
    nodes=[]
    for f in resp[begin:end]:
        p=f['data'];require(all(p[k]==before[k] for k in ('sourceInstance','providerPid','sourceEpoch','sourceRevision')) and p['query']=='' and p['visibleOnly'] is False,'oracle binding/scope');nodes.extend(p['nodes'])
    compare_structure(reference,nodes);results.append({'baseline':label,'nodes':len(nodes),'epoch':before['sourceEpoch'],'revision':before['sourceRevision'],'sha256':before['structureSha256']})
(out/'oracle-ab-check.json').write_text(json.dumps({'status':'PASSED_SCOPED','input_sha256':report['inputs']['input']['sha256'],'comparisons':results,'oracle':'independent liteHTML model, test-only diagnostic log; no production IPC operation'},indent=2)+'\n')
