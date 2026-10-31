#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Independent oracle derived from captured Provider responses, never Consumer diff."""
import hashlib, json, re, sys
from collections import Counter
from pathlib import Path

out=Path(sys.argv[1]); report=json.loads((out/'report.json').read_text()); serial=(out/'serial.log').read_bytes()
def require(condition, reason):
    if not condition: raise AssertionError(reason)
def read(seq, direction): return json.loads((out/f'{seq:02d}-{direction}.json').read_bytes())
frames=report['frames']; responses=[read(f['sequence'],'resp') for f in frames if f['direction']=='RESP']
requests=[read(f['sequence'],'req') for f in frames if f['direction']=='REQ']
require(len(responses)==len(requests), 'unpaired frames')
starts=[i for i,q in enumerate(requests) if q.get('op')=='snapshot_begin']
require(len(starts)==3 and starts[0]==0, 'expected A, interrupted B, recovery B')
segments=[(requests[x:y],responses[x:y]) for x,y in zip(starts,starts[1:]+[len(requests)])]
failed=segments[1][1]
require(len(failed)>2 and failed[-1]['status']=='STALE_CURSOR', 'no interrupted stale session')
require(all(p['status']=='OK' and not p['complete'] for p in failed[:-1]), 'invalid interrupted pages')
old=failed[0]['sessionId']
require(all(p['sessionId']==old for p in failed[:-1]), 'mixed interrupted sessions')
for i,p in enumerate(failed[:-1]):
    require(p['pageSequence']==str(i+1) and all(p[k]==failed[0][k] for k in ('sourceInstance','sourceEpoch','sourceRevision','scrollY')), 'interrupted session continuity')
    if i: require(segments[1][0][i]=={'op':'snapshot_next','sourceInstance':failed[0]['sourceInstance'],'cursor':failed[i-1]['cursor']}, 'interrupted cursor continuity')
require(segments[1][0][-1]['cursor']==failed[-2]['cursor'], 'stale request did not use interrupted cursor')
baselines=[]
for label,(reqs,pages) in zip(('A','B'),(segments[0],segments[2])):
    first=pages[0]; nodes=[]
    require(reqs[0]=={'op':'snapshot_begin','maxNodes':8}, 'begin request')
    for i,(p,q) in enumerate(zip(pages,reqs)):
        require(p['status']=='OK' and p['pageSequence']==str(i+1) and p['complete']==(i==len(pages)-1), 'page sequence')
        require(all(p[k]==first[k] for k in ('sourceInstance','sourceEpoch','sourceRevision','sessionId','scrollY')), 'session continuity')
        require(p['sourceValid'] is True and p['query']=='' and p['visibleOnly'] is False and p['hasNext']==(i!=len(pages)-1) and p['traversalComplete']==(i==len(pages)-1), 'page metadata')
        if i: require(q=={'op':'snapshot_next','sourceInstance':first['sourceInstance'],'cursor':pages[i-1]['cursor']}, 'cursor continuity')
        nodes.extend(p['nodes'])
    require(nodes and len({n['id'] for n in nodes})==len(nodes), 'empty or duplicate nodes')
    baseline={'sourceInstance':first['sourceInstance'],'sourceEpoch':first['sourceEpoch'],'sourceRevision':first['sourceRevision'],'sessionId':first['sessionId'],'scrollY':first['scrollY'],'nodes':nodes}
    baselines.append(baseline);(out/('baseline-'+label+'.json')).write_text(json.dumps(baseline,ensure_ascii=False,indent=2)+'\n')
require(old not in (baselines[0]['sessionId'], baselines[1]['sessionId']), 'stale session reused')
events=json.loads((out/'qmp-events.json').read_text())
ready=serial.index(b'SSG_RECOVERY_INJECTION_READY'); scroll=serial.index(b'BROWSER_SCROLL value=',ready); stale=serial.index(b'SSG_RECOVERY_STALE discarded=1',scroll); commit=serial.index(b'SSG_BASELINE_B_COMMITTED',stale)
require(serial.count(b'SSG_BASELINE_B_COMMITTED')==1 and serial.count(b'SSG_CONSUMER_DIFF_DONE status=OK')==1, 'unexpected partial commit or diff')
last_page_frame=[f for f in frames if f['direction']=='RESP'][starts[2]-2]
stale_frame=[f for f in frames if f['direction']=='RESP'][starts[2]-1]
require(last_page_frame['end'] <= ready < scroll < stale_frame['begin'] < stale_frame['end'] <= stale < commit, 'IPC and input event order')
keyevents=[e for e in events if e['command']=='input-send-event' and any(x.get('data',{}).get('key',{}).get('data')=='pgdn' for x in e['arguments']['events'])]
require(keyevents and all(ready <= e['serial_offset'] <= scroll for e in keyevents), 'input outside recovery window')
require(b'SSG_RECOVERY_LAST_GOOD session='+baselines[0]['sessionId'].encode() in serial[stale:commit], 'last good baseline not retained')
a,b=baselines
require(len(a['nodes'])==len(b['nodes']), 'structure length changed')
require(a['sourceInstance']==b['sourceInstance'] and a['sourceEpoch']==b['sourceEpoch'] and a['sessionId']!=b['sessionId'] and a['scrollY']!=b['scrollY'], 'A/B identity or scroll')
require(re.search(rb'BROWSER_SCROLL value='+str(b['scrollY']).encode()+rb'\b',serial), 'no matching real browser scroll')
expected=[{'kind':'ScrollChanged','id':'','before':a['scrollY'],'after':b['scrollY']}]
for x,y in zip(a['nodes'],b['nodes']):
    require(all(x[k]==y[k] for k in ('id','parent','role','tag')), 'identity or structure changed')
    require(x.get('text')==y.get('text') and x.get('href')==y.get('href'), 'unexpected text or href change')
    for kind,keys in (('WindowGeometryChanged',('bounds','fragments')),('VisibilityChanged',('visibility','visibleBounds','visibleFragments'))):
        before={k:x[k] for k in keys};after={k:y[k] for k in keys}
        if before!=after: expected.append({'kind':kind,'id':x['id'],'before':before,'after':after})
m=re.search(rb'^SSG_CONSUMER_DIFF_JSON (.+)\r?$',serial,re.M);require(m is not None,'missing diff JSON');actual=json.loads(m.group(1))
require(actual['status']=='OK' and actual['changes']==expected, 'consumer diff disagrees with independent calculation')
require(report['after']==report['display'], 'resource counters changed')
require(hashlib.sha256((out/'input.html').read_bytes()).hexdigest()==report['inputs']['input']['sha256'], 'document hash changed')
(out/'diff.json').write_text(json.dumps(actual,ensure_ascii=False,indent=2)+'\n')
(out/'independent-check.json').write_text(json.dumps({'status':'PASSED_SCOPED','pages':[len(segments[0][1]),len(segments[2][1])], 'interrupted_pages':len(failed)-1, 'stale_session':old, 'recovered_session':b['sessionId'],'nodes':[len(a['nodes']),len(b['nodes'])],'scroll':[a['scrollY'],b['scrollY']],'change_counts':dict(Counter(c['kind'] for c in expected)),'identity':'same complete preorder ID/parent/role/tag within one epoch','document_sha256':report['inputs']['input']['sha256'],'resource_counters_match':True},indent=2)+'\n')
print('independent A/B verification passed')
