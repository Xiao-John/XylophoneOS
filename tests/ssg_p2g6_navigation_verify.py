#!/usr/bin/env python3
"""Check paging and identity boundary against actual guest IPC and input."""
import json, re, sys
from ssg_browser_structure import decode_capture, validate_oracle, compare_structure
from pathlib import Path
out=Path(sys.argv[1]); report=json.loads((out/'report.json').read_text()); serial=(out/'serial.log').read_bytes()
def require(v,m):
    if not v: raise AssertionError(m)
f=report['frames']; req=[x for x in f if x['direction']=='REQ']; resp=[x for x in f if x['direction']=='RESP']
qs=[json.loads((out/x['file']).read_bytes()) for x in req]; rs=[json.loads((out/x['file']).read_bytes()) for x in resp]
starts=[i for i,x in enumerate(qs) if x.get('op')=='snapshot_begin']; require(len(starts)==3 and starts[0]==1,'three paging sessions required')
a0,b0,c0=starts; require(qs[0]['op']=='snapshot' and rs[0]['status']=='OK','old scene missing')
require(rs[c0-2]['status']=='STALE_CURSOR' and qs[c0-2]['cursor']==rs[c0-3]['cursor'],'old cursor not rejected')
require(qs[c0-1]['op']=='detail' and rs[c0-1]['status']=='SOURCE_REPLACED','old node not rejected')
require(qs[c0-1]['sourceEpoch']==rs[a0]['sourceEpoch'] and rs[c0]['sourceEpoch']!=rs[a0]['sourceEpoch'],'epoch boundary')
require(rs[c0-1]['sourceEpoch']==rs[c0]['sourceEpoch'] and rs[c0]['sourceInstance']==rs[a0]['sourceInstance'],'source mismatch')
for label,start,end in [('A',a0,b0),('C',c0,len(qs))]:
    pages=rs[start:end]; first=pages[0]; nodes=[]
    for j,p in enumerate(pages):
        require(p['status']=='OK' and p['pageSequence']==str(j+1) and p['complete']==(j==len(pages)-1),'page completeness')
        require(all(p[k]==first[k] for k in ('sourceInstance','sourceEpoch','sourceRevision','sessionId','scrollY')),'page identity')
        require(p['query']=='' and not p['visibleOnly'] and p['sourceValid'],'scope')
        if j: require(qs[start+j]=={'op':'snapshot_next','sourceInstance':first['sourceInstance'],'cursor':pages[j-1]['cursor']},'cursor continuity')
        nodes.extend(p['nodes'])
    require(nodes and len({n['id'] for n in nodes})==len(nodes),'duplicate or empty nodes')
    (out/('baseline-'+label+'.json')).write_text(json.dumps({'metadata':first,'nodes':nodes},ensure_ascii=False,indent=2)+'\n')
require(b'SSG_RELOAD_DIFF status=RESET_REQUIRED changes=0' in serial and b'SSG_BASELINE_B_COMMITTED' not in serial and b'SSG_CONSUMER_DIFF_DONE status=OK' not in serial,'cross document result')
ready=serial.index(b'SSG_RECOVERY_INJECTION_READY'); loaded=serial.index(b'BROWSER_LOADED path=/web/start.html',ready); events=json.loads((out/'qmp-events.json').read_text()); clicks=[e for e in events if e['command']=='input-send-event' and any(x.get('type')=='btn' and x.get('data',{}).get('button')=='left' for x in e['arguments']['events'])]
require(len(clicks)==2 and resp[c0-3]['end'] <= ready <= clicks[0]['serial_offset'] <= clicks[1]['serial_offset'] <= loaded < resp[c0-2]['begin'], 'navigation input ordering')
cap=decode_capture(serial); oracles=cap['oracles']; require(len(oracles)==5,'oracle capture count')
for label,begin,end,ob,oa,path,sha in [('A',a0,b0,oracles[0],oracles[1],'/web/ssg.html',report['inputs']['input']['sha256']),('C',c0,len(qs),oracles[3],oracles[4],'/web/start.html',report['inputs']['link_target']['sha256'])]:
    before,after=ob['data'],oa['data']; require(before['document']==after['document']==path,'oracle document')
    # Existing P2F validator fixes its document path; normalize only that field after verifying it above.
    x=dict(before,document='/web/ssg.html'); y=dict(after,document='/web/ssg.html')
    reference=validate_oracle(x,sha,'before'); validate_oracle(y,sha,'after')
    for k in ('document','inputSha256','sourceInstance','providerPid','sourceEpoch','sourceRevision','nodeCount','structureSha256','nodes'): require(before[k]==after[k], 'oracle changed '+k)
    require(req[begin]['end']<=ob['begin']<ob['end']<=resp[begin]['begin'] and req[end-1]['end']<=oa['begin']<oa['end']<=resp[end-1]['begin'],'oracle order')
    nodes=[]
    for p in rs[begin:end]:
        require(all(p[k]==before[k] for k in ('sourceInstance','providerPid','sourceEpoch','sourceRevision')),'oracle source binding'); nodes.extend(p['nodes'])
    compare_structure(reference,nodes)
    if label=='A': old_reference=reference
    else: require(reference!=old_reference and any('LINK_TARGET_REACHED' in n.get('text','') for n in reference) and not any(n['role']=='link' for n in reference) and any(n['role']=='link' for n in old_reference),'fixture content difference')
require(report['after']==report['display'] and re.search(rb'SSG_SESSION consumer_wait=0 outcome=1 code=0',serial) and re.search(rb'SSG_SESSION provider_wait=0 outcome=1 code=0',serial),'cleanup')
(out/'independent-check.json').write_text(json.dumps({'status':'PASSED_SCOPED','old_epoch':rs[a0]['sourceEpoch'],'new_epoch':rs[c0]['sourceEpoch'],'sessions':[rs[x]['sessionId'] for x in starts], 'interrupted_pages':c0-b0-2,'A_nodes':sum(len(p['nodes']) for p in rs[a0:b0]),'C_nodes':sum(len(p['nodes']) for p in rs[c0:]),'old_cursor':'STALE_CURSOR','old_node':'SOURCE_REPLACED','diff':'RESET_REQUIRED','resources_match':True},indent=2)+'\n')
