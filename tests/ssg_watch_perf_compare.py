#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compare measured IPC for the common first scroll in independently checked runs."""
import argparse
import json
from pathlib import Path
import re
from ssg_p3b_verify import frames, require


def wire_stats(data):
    frames_found = re.findall(rb'^P3B_FRAME_BEGIN (browser|notes) (REQ|RESP) \d+ (\d+) \d+\r?$', data, re.MULTILINE)
    return {'requests': sum(direction == b'REQ' for _, direction, _ in frames_found),
            'ipc_bytes_with_headers': sum(int(size) + 12 for _, _, size in frames_found)}


def active_ns(samples):
    result = {}
    for slot in ('browser', 'notes'):
        result[slot] = sum(int(source['endedMonotonicNs']) - int(source['startedMonotonicNs'])
                           for sample in samples for source in sample['sources'] if source['slot'] == slot)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--p3b', type=Path, required=True)
    p.add_argument('--watch', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    old_check = json.loads((a.p3b / 'independent-check.json').read_text())
    new_check = json.loads((a.watch / 'independent-check.json').read_text())
    require(old_check['status'] == new_check['status'] == 'PASSED_SCOPED' and old_check['case'] == 'browser-scroll' and new_check['case'] == 'scroll', 'runs are not independently verified')
    old_report = json.loads((a.p3b / 'report.json').read_text())
    new_report = json.loads((a.watch / 'report.json').read_text())
    for name in ('image', 'browser', 'notes', 'input'):
        require(old_report['inputs'][name]['sha256'] == new_report['inputs'][name]['sha256'], 'fixture or provider mismatch')
    old_serial = (a.p3b / 'serial.log').read_bytes()
    new_serial = (a.watch / 'serial.log').read_bytes()
    marker = new_serial.find(b'P3C_CYCLE_READY cycle=2 ')
    require(marker >= 0, 'second watch cycle missing')
    old_data, new_data = frames(old_serial), frames(new_serial)
    old_samples = [old_data[('aggregate', 'BASELINE', i)] for i in (0, 1)]
    new_samples = [new_data[('aggregate', 'BASELINE', i)] for i in (1, 2)]
    def browser(sample):
        return next(source for source in sample['sources'] if source['slot'] == 'browser')
    old_scroll = [browser(sample)['scrollY'] for sample in old_samples]
    new_scroll = [browser(sample)['scrollY'] for sample in new_samples]
    require(old_scroll == new_scroll and old_scroll[0] != old_scroll[1], 'the compared scroll event differs')
    result = {'status': 'PARTIAL', 'scope': 'same image, provider binaries, synthetic documents and first real PageDown; two source observations per run',
              'scroll_before_after': old_scroll,
              'p3b_two_sample': {**wire_stats(old_serial), 'source_observation_ns': active_ns(old_samples),
                                 'whole_run_wall_seconds': old_report['elapsed_seconds']},
              'watch_first_two_cycles': {**wire_stats(new_serial[:marker]), 'source_observation_ns': active_ns(new_samples),
                                         'three_cycle_whole_run_wall_seconds': new_report['elapsed_seconds']},
              'interpretation': 'Both implementations pull complete source baselines on every cycle. The watch emits bounded summaries but does not prove a reduction in provider IPC.',
              'limits': ['The independent third full-baseline mode was not separately run.',
                         'Whole-run times include different cycle counts and waits and are not a head-to-head timing comparison.',
                         'CPU time and absolute peak memory were not measured.',
                         'Only the observed first scroll was compared; missed intermediate updates remain unknown.']}
    a.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
