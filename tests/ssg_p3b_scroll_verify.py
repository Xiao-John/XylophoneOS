#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Recompute a real Browser scroll Diff while Notes remains alive."""
import argparse
import json
from pathlib import Path
import re
from ssg_p3b_verify import frames, require, check_source_metadata, check_wiring
from ssg_p3b_dynamic_verify import check_browser, notes_segment, verify_qmp_key, verify_browser_receipt
from ssg_browser_structure import decode_capture

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('output', type=Path)
a = p.parse_args()
out = a.output
report = json.loads((out / 'report.json').read_text())
verify_browser_receipt(out / 'browser.receipt.json', report)
require(report['case'] == 'browser-scroll' and 'real_ps2_browser-scroll' in report['events'], 'missing PS/2 input')
serial = (out / 'serial.log').read_bytes()
verify_qmp_key(report, serial, b'P3B_BROWSER_SCROLL_READY', 'pgdn', b'BROWSER_SCROLL value=')
f = frames(serial)
a0, a1 = [f[('aggregate', 'BASELINE', i)] for i in (0, 1)]
s0, s1 = [{v['slot']: v for v in a['sources']} for a in (a0, a1)]
for sample in (s0, s1):
    for source in sample.values(): check_source_metadata(source)
check_wiring(serial, report, s0)
require(a0['status'] == a1['status'] == 'AGGREGATE_COMPLETE_OBSERVED', 'incomplete samples')
records = {}
for slot in ('browser', 'notes'):
    req = sorted((seq, v) for (s, d, seq), v in f.items() if s == slot and d == 'REQ')
    resp = sorted((seq, v) for (s, d, seq), v in f.items() if s == slot and d == 'RESP')
    require([n for n, _ in req] == [n for n, _ in resp] == list(range(1, len(req)+1)), 'unpaired frames')
    records[slot] = [(q, r) for (_, q), (_, r) in zip(req, resp)]
br = records['browser']
starts = [i for i, (q, _) in enumerate(br) if q.get('op') == 'snapshot_begin']
oracles = decode_capture(serial)['oracles']
require(len(starts) == 2 and len(oracles) == 4, 'missing Browser captures')
a_nodes, old = check_browser(br[:starts[1]], oracles[:2], s0['browser'], report)
b_nodes, new = check_browser(br[starts[1]:], oracles[2:], s1['browser'], report)
require(a_nodes == b_nodes and old['sourceInstance'] == new['sourceInstance'] and old['sourceEpoch'] == new['sourceEpoch'], 'Browser identity or content changed')
pages = (br[:starts[1]], br[starts[1]:])
raw = [[n for _, response in sample for n in response['nodes']] for sample in pages]
geometry = visibility = other = 0
for x, y, ax, ay in zip(raw[0], raw[1], s0['browser']['nodes'], s1['browser']['nodes']):
    require(x['id'] == y['id'] and x['parent'] == y['parent'], 'node identity changed')
    for key in ('bounds', 'fragments', 'visibleBounds', 'visibleFragments', 'visibility', 'fragmentsComplete'):
        require(ax.get(key) == x.get(key) and ay.get(key) == y.get(key), 'aggregate geometry differs from IPC')
    geometry += int(x['bounds'] != y['bounds'] or x['fragments'] != y['fragments'])
    visibility += int(x['visibility'] != y['visibility'] or x['visibleBounds'] != y['visibleBounds'] or x['visibleFragments'] != y['visibleFragments'])
    other += int(x.get('text') != y.get('text')) + int(x.get('href') != y.get('href'))
before, after = s0['browser']['scrollY'], s1['browser']['scrollY']
require(before != after and after > 0 and all(response['scrollY'] == before for _, response in pages[0]) and all(response['scrollY'] == after for _, response in pages[1]), 'actual scroll not reflected')
require(re.search(rb'BROWSER_SCROLL value=' + str(after).encode() + rb'\b', serial), 'guest Browser did not report scroll')
marker = re.search(rb'P3B_SCROLL before=(\d+) after=(\d+) scroll=(\d+) geometry=(\d+) visibility=(\d+) other=(\d+) notes=UNCHANGED', serial)
require(marker and list(map(int, marker.groups())) == [before, after, 1, geometry, visibility, other], 'Diff counts do not match independent recomputation')
diffs = re.findall(rb'^P3B_AGGREGATE_DIFF (\{.*\})\r?$', serial, re.MULTILINE)
require(len(diffs) == 1 and json.loads(diffs[0]) == {'status': 'OK', 'semantics': 'per-source-non-atomic', 'browser': 'CHANGED', 'notes': 'UNCHANGED'}, 'aggregate Diff classification')
segments = []
for pair in records['notes']:
    if pair[0].get('op') == 'snapshot': segments.append([])
    segments[-1].append(pair)
require(len(segments) == 2, 'missing Notes reread')
first, second = [notes_segment(s, report['processes']['notes']) for s in segments]
expected = (out / 'synthetic-input.txt').read_text()
require(first[2] == second[2] == expected and first[3] == second[3] and first[4] is None and second[4] is None, 'Notes changed')
require(report['resources_restored'] and all('reaped=1 cancelled=0 outcome=1 code=0' in line for line in report['source_exits']), 'shutdown/resources')
result = {'status': 'PASSED_SCOPED', 'case': report['case'], 'scroll_before': before, 'scroll_after': after,
          'scroll_changes': 1, 'geometry_changes': geometry, 'visibility_changes': visibility, 'other_changes': other,
          'notes': 'UNCHANGED', 'notes_presentation': 'hidden-no-input', 'source_exits': report['source_exits']}
(out / 'independent-check.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
