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
require(len(responses)==len(requests)==68, 'expected two 34-page sessions')
baselines=[]
for start in (0,34):
    pages=responses[start:start+34]; reqs=requests[start:start+34]; first=pages[0]; nodes=[]
    require(reqs[0]=={'op':'snapshot_begin','maxNodes':8}, 'begin request')
    for i,(p,q) in enumerate(zip(pages,reqs)):
        require(p['status']=='OK' and p['pageSequence']==str(i+1) and p['complete']==(i==33), 'page sequence')
        require(all(p[k]==first[k] for k in ('sourceInstance','sourceEpoch','sourceRevision','sessionId','scrollY')), 'session continuity')
        require(p['sourceValid'] is True and p['query']=='' and p['visibleOnly'] is False and p['hasNext']==(i!=33) and p['traversalComplete']==(i==33), 'page metadata')
        if i: require(q=={'op':'snapshot_next','sourceInstance':first['sourceInstance'],'cursor':pages[i-1]['cursor']}, 'cursor continuity')
        nodes.extend(p['nodes'])
    require(len(nodes)==267 and len({n['id'] for n in nodes})==267, 'node count or duplicates')
    baseline={'sourceInstance':first['sourceInstance'],'sourceEpoch':first['sourceEpoch'],'sourceRevision':first['sourceRevision'],'sessionId':first['sessionId'],'scrollY':first['scrollY'],'nodes':nodes}
    baselines.append(baseline);(out/('baseline-A.json' if start==0 else 'baseline-B.json')).write_text(json.dumps(baseline,ensure_ascii=False,indent=2)+'\n')
a,b=baselines
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
(out/'independent-check.json').write_text(json.dumps({'status':'PASSED_SCOPED','pages':[34,34],'nodes':[len(a['nodes']),len(b['nodes'])],'scroll':[a['scrollY'],b['scrollY']],'change_counts':dict(Counter(c['kind'] for c in expected)),'identity':'same complete preorder ID/parent/role/tag within one epoch','document_sha256':report['inputs']['input']['sha256'],'resource_counters_match':True},indent=2)+'\n')
print('independent A/B verification passed')
