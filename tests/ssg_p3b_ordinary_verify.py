#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check explicit aggregate output of the ordinary, non-frame-logging build."""
import argparse
import json
from pathlib import Path
from ssg_p3b_verify import frames, require
from ssg_browser_structure import decode_capture, validate_oracle

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('output', type=Path)
a = p.parse_args()
out = a.output
report = json.loads((out / 'report.json').read_text())
require(report['case'] == 'ordinary', 'wrong case')
serial = (out / 'serial.log').read_bytes()
f = frames(serial)
require(set(f) == {('aggregate', 'BASELINE', 0)}, 'ordinary mode logged raw request/response frames')
aggregate = f[('aggregate', 'BASELINE', 0)]
require(aggregate['status'] == 'AGGREGATE_COMPLETE_OBSERVED' and aggregate['globalAtomicSnapshot'] == 'NOT_IMPLEMENTED', 'aggregate incomplete')
sources = {v['slot']: v for v in aggregate['sources']}
require(sources['notes']['presentation'] == 'hidden-session-no-surface-no-input', 'hidden scope omitted')
reference = decode_capture(serial)['oracles']
require(len(reference) == 2, 'oracle pair missing')
before, after = [x['data'] for x in reference]
expected = validate_oracle(before, report['inputs']['input']['sha256'], 'before')
validate_oracle(after, report['inputs']['input']['sha256'], 'after')
require(before['nodes'] == after['nodes'] and before['sourceEpoch'] == after['sourceEpoch'] and before['providerPid'] == str(report['processes']['browser']), 'oracle changed')
browser = sources['browser']
require(browser['instance'] == before['sourceInstance'] and browser['epoch'] == before['sourceEpoch'] and len(browser['nodes']) == len(expected), 'Browser aggregate identity/count')
path_to_id = {}
for node, ref in zip(browser['nodes'], expected):
    ident = node['id']
    require(ident == {'slot': 'browser', 'sourceInstance': before['sourceInstance'], 'sourceEpoch': before['sourceEpoch'], 'localNodeId': ident['localNodeId']}, 'Browser namespace')
    require(node['parent'] == ('0' if not ref['parentPath'] else path_to_id[ref['parentPath']]), 'Browser parent')
    for key in ('role', 'tag', 'text', 'href'):
        require((key in node) == (key in ref) and node.get(key) == ref.get(key), 'Browser data mismatch')
    path_to_id[ref['path']] = ident['localNodeId']
text = (out / 'synthetic-input.txt').read_text()
notes = sources['notes']
require(notes['document']['text'] == text and notes['document']['utf16Units'] == len(text.encode('utf-16-le')) // 2, 'Notes content mismatch')
require(notes['document']['id']['slot'] == 'notes' and notes['instance'] != browser['instance'], 'Notes namespace')
require(report['resources_restored'], 'resources not restored')
result = {'status': 'PASSED_SCOPED', 'scope': 'ordinary non-diagnostic executable, explicit aggregate output; no raw IPC capture',
          'browser_nodes': len(expected), 'notes_utf16_units': notes['document']['utf16Units'], 'source_exits': report['source_exits'], 'resources_restored': True}
(out / 'independent-check.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
