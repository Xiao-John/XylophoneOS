#!/usr/bin/env python3
"""Validate real guest retry exhaustion from captured IPC and PS/2 event ordering."""
import json, re, sys
from pathlib import Path
out = Path(sys.argv[1]); report = json.loads((out/'report.json').read_text()); serial = (out/'serial.log').read_bytes()
def require(v, reason):
    if not v: raise AssertionError(reason)
frames = report['frames']; req = [f for f in frames if f['direction']=='REQ']; resp = [f for f in frames if f['direction']=='RESP']
require(len(req)==len(resp), 'unpaired frames')
qs = [json.loads((out/f['file']).read_bytes()) for f in req]; rs = [json.loads((out/f['file']).read_bytes()) for f in resp]
starts = [i for i,q in enumerate(qs) if q.get('op')=='snapshot_begin']; require(len(starts)==4 and starts[0]==0, 'expected A and three attempts')
segments = [list(range(x,y)) for x,y in zip(starts,starts[1:]+[len(qs)])]; sessions=[]
for j,seg in enumerate(segments):
    first=rs[seg[0]]; sessions.append(first['sessionId']); require(qs[seg[0]]=={'op':'snapshot_begin','maxNodes':8}, 'begin mismatch')
    successful=seg if j==0 else seg[:-1]
    for n,i in enumerate(successful):
        p=rs[i]; require(p['status']=='OK' and p['pageSequence']==str(n+1), 'page sequence')
        require(all(p[k]==first[k] for k in ('sessionId','sourceEpoch','sourceInstance','sourceRevision','scrollY')), 'session continuity')
        if n: require(qs[i]=={'op':'snapshot_next','sourceInstance':first['sourceInstance'],'cursor':rs[i-1]['cursor']}, 'cursor continuity')
    if j==0:
        require(rs[seg[-1]]['complete'] and all(not rs[i]['complete'] for i in seg[:-1]), 'A incomplete')
        nodes=[n for i in seg for n in rs[i]['nodes']]; require(len(nodes)==267 and len({n['id'] for n in nodes})==len(nodes), 'A node count or identity')
        (out/'baseline-A.json').write_text(json.dumps({'metadata':first,'nodes':nodes},ensure_ascii=False,indent=2)+'\n')
    else:
        require(len(successful)==3 and rs[seg[-1]]['status']=='STALE_CURSOR', 'attempt not invalidated after three pages')
        require(qs[seg[-1]]['cursor']==rs[seg[-2]]['cursor'], 'stale cursor mismatch')
require(len(set(sessions))==4, 'session reused')
ready=list(re.finditer(rb'SSG_RECOVERY_INJECTION_READY pages=3 session=(\d+)',serial)); scroll=list(re.finditer(rb'BROWSER_SCROLL value=(\d+)',serial)); stale=list(re.finditer(rb'SSG_RECOVERY_STALE discarded=1',serial)); good=list(re.finditer(rb'SSG_RECOVERY_LAST_GOOD session=(\d+) nodes=(\d+)',serial)); require(len(ready)==len(scroll)==len(stale)==len(good)==3, 'event counts')
events=json.loads((out/'qmp-events.json').read_text()); keys=[e for e in events if e['command']=='input-send-event' and any(x.get('data',{}).get('key',{}).get('data')=='pgdn' for x in e['arguments']['events'])]; require(len(keys)==6, 'PS/2 input count')
for j,seg in enumerate(segments[1:]):
    require(ready[j].group(1).decode()==sessions[j+1] and good[j].group(1).decode()==sessions[0] and good[j].group(2)==b'267', 'retained baseline identity')
    require(resp[seg[-2]]['end'] <= ready[j].start() <= keys[2*j]['serial_offset'] <= keys[2*j+1]['serial_offset'] <= scroll[j].start() < resp[seg[-1]]['begin'] < resp[seg[-1]]['end'] <= stale[j].start() < good[j].start(), 'input / rejection ordering')
require(b'SSG_BASELINE_B_COMMITTED' not in serial and b'SSG_CONSUMER_DIFF_' not in serial, 'partial B or diff')
require(b'SSG_RECOVERY_FAILED status=RESET_REQUIRED budget=2' in serial and report['after']==report['display'], 'budget or resources')
require(re.search(rb'SSG_SESSION consumer_wait=0 outcome=1 code=1',serial) and re.search(rb'SSG_SESSION provider_wait=0 outcome=1 code=0',serial), 'exit status')
(out/'independent-check.json').write_text(json.dumps({'status':'PASSED_SCOPED','sessions':sessions,'A_nodes':len(nodes),'attempt_pages':[len(x)-1 for x in segments[1:]],'scroll_values':[int(x.group(1)) for x in scroll], 'result':'RESET_REQUIRED','consumer_exit':1,'provider_exit':0,'resources_match':True},indent=2)+'\n')
