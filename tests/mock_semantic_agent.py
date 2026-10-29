#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Independent deterministic Observe -> Propose consumer. Never authorizes/executes."""
import json,sys
def propose(snapshot):
    if snapshot.get('metadata',{}).get('provider')=='qt-widget-v1':
        for item in snapshot['nodes']:
            if (item['role']=='textbox' and item.get('enabled') and
                item.get('visibility')=='locally-visible' and not item['sensitive'] and not item.get('readOnly',False) and
                'intentRef' in item and 'set_text' in item['actions']):
                ref=item['intentRef']
                return {'version':1,'epoch':ref['epoch'],'id':ref['id'],'revision':ref['revision'],
                        'action':'set_text','value':'mock-agent-verified'}
        raise ValueError('no authorized adapter target in SSG')
    if snapshot.get('version')!=1 or snapshot.get('scope')!='application-local-demo':
        raise ValueError('unsupported snapshot')
    for item in snapshot['controls']:
        if item['role']=='textbox' and item.get('enabled') and item.get('visible') and not item['externalEffect']:
            return {'version':1,'epoch':snapshot['epoch'],'id':item['id'],
                    'revision':item['revision'],'action':'set_text','value':'mock-agent-verified'}
    raise ValueError('no admitted local target')
if __name__=='__main__':
    raw=sys.stdin.read(65537)
    if len(raw)>65536:raise ValueError('snapshot budget')
    print(json.dumps(propose(json.loads(raw)),separators=(',',':')))
