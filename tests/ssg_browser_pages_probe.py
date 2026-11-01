#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Capture real Browser IPC and, explicitly, qualify it against a guest Oracle.

--require-oracle requires the separate test Browser build and a matching build
receipt. Plain observation never qualifies completeness. Every run uses a new
directory; frozen P2D/P2E evidence is never changed.
"""
import argparse
import hashlib
import json
import os
import posixpath
import re
import struct
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT / 'scripts')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from work_disk import transfer
from process_smoke import command, resources
from task_smoke import send_bytes, pump
from ssg_browser_structure import decode_capture, validate_capture, validate_resource_rejection
from ssg_public_paths import portable
import shutil

p = argparse.ArgumentParser(description=__doc__)
for name in ('image', 'session', 'browser', 'consumer', 'output', 'input'):
    p.add_argument('--' + name, type=Path, required=True)
p.add_argument('--image-format', choices=('auto', 'floppy', 'iso'), default='auto')
p.add_argument('--browser-receipt', type=Path)
mode = p.add_mutually_exclusive_group()
mode.add_argument('--require-oracle', action='store_true')
mode.add_argument('--expect-resource-limit', action='store_true')
p.add_argument('--link-hit', action='store_true',
               help='After completed paging, test one Consumer-selected visible link with real PS/2 input')
a = p.parse_args()
if a.link_hit and not a.require_oracle:
    p.error('--link-hit requires --require-oracle')
inputs = {name: getattr(a, name).resolve(strict=True)
          for name in ('image', 'session', 'browser', 'consumer', 'input')}
out = a.output.resolve()
out.mkdir(parents=True, exist_ok=False)
sha = lambda data: hashlib.sha256(data).hexdigest()
report = {'status': 'FAILED', 'qualification': 'NOT_RUN', 'gate_A_overall': 'NOT_QUALIFIED',
          'gate_B': 'NOT_RUN', 'gate_C': 'NOT_RUN',
          'inputs': {name: {'path': str(path), 'sha256': sha(path.read_bytes())}
                     for name, path in inputs.items()},
          'geometry': {'status': 'NOT_RUN'}, 'performance': 'NOT_QUALIFIED'}
fixture = out / 'input.html'
fixture.write_bytes(inputs['input'].read_bytes())
report['inputs']['input']['sha256'] = sha(fixture.read_bytes())
for name in ('ssg_browser_pages_probe.py', 'ssg_browser_structure.py'):
    source = ROOT / 'tests' / name
    report['inputs'][name] = {'path': str(source), 'sha256': sha(source.read_bytes())}
image_format = a.image_format
if image_format == 'auto':
    image_format = 'iso' if inputs['image'].suffix.lower() == '.iso' else 'floppy'
report['image_format'] = image_format
g = None
disk = None
capture = None

def public_mappings():
    mappings = [("XOS_IMAGE", inputs["image"]), ("XOS_SESSION_ELF", inputs["session"]),
                ("XOS_BROWSER_ELF", inputs["browser"]), ("XOS_CONSUMER_ELF", inputs["consumer"]),
                ("XOS_INPUT", inputs["input"]), ("XOS_TEST_OUT", out),
                ("XOS_BROWSER_BUILD_DIR", inputs["browser"].parent),
                ("XOS_WORK_DISK", disk), ("XOS_QMP_SOCKET", g.qmp_path if g else None),
                ("XOS_QEMU", g.command[0] if g else None), ("XOS_PYTHON", sys.executable),
                ("XOS_CXX", shutil.which("x86_64-elf-g++")),
                ("XOS_CC", shutil.which("x86_64-elf-gcc")),
                ("XOS_AR", shutil.which("x86_64-elf-ar"))]
    for name in ("XOS_SDK_PREFIX", "XOS_BUILD_DIR", "XOS_QT_SOURCE", "XOS_HOST_QT",
                 "XOS_BINUTILS", "XOS_BASE_ROOT", "XOS_WORKSPACE", "XOS_TOOLCHAIN_PREFIX",
                 "XOS_HOST_HOME", "XOS_CODEX_RUNTIME", "XOS_PYTHON_FRAMEWORK"):
        if os.environ.get(name):
            mappings.append((name, os.environ[name]))
    return mappings
events = []


def require(ok, message):
    if not ok:
        raise ValueError(message)


def verify_test_receipt():
    path = (a.browser_receipt or inputs['browser'].with_suffix('.receipt.json')).resolve(strict=True)
    raw = path.read_bytes()
    receipt = json.loads(raw)
    require(receipt.get('test_structure_oracle') is True, 'Browser was not explicitly built with the test Oracle')
    require(receipt.get('elf_sha256') == report['inputs']['browser']['sha256'], 'Browser ELF differs from build receipt')
    for name in ('build.py', 'main.cpp', 'view.hpp', 'test_structure_oracle.hpp',
                 'content.hpp', 'scene_geometry.hpp'):
        relative = 'src/ports/aurora_browser/' + name
        matches = [digest for filename, digest in receipt.get('inputs', {}).items()
                   if filename.endswith('/' + relative)]
        require(matches == [sha((ROOT / relative).read_bytes())], 'Browser receipt source mismatch: ' + relative)
    public_receipt = (json.dumps(portable(receipt, public_mappings(), strict=True), indent=2) + '\n').encode()
    (out / 'browser.receipt.json').write_bytes(public_receipt)
    report['inputs']['browser_receipt'] = {'path': str(out / 'browser.receipt.json'), 'sha256': sha(public_receipt), 'original_sha256': sha(raw)}
    report['source_checkout'] = {
        'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'tracked_changes': subprocess.check_output(['git', 'diff', '--name-only', 'HEAD'], cwd=ROOT, text=True).splitlines(),
        'tracked_diff_sha256': sha(subprocess.check_output(['git', 'diff', 'HEAD'], cwd=ROOT)),
        'binding': 'Browser ELF and current Browser source hashes are checked against browser.receipt.json',
    }


def qmp(execute, arguments=None):
    events.append({'command': execute, 'arguments': arguments, 'serial_offset': len(g.output)})
    result = g.qmp(execute, arguments)
    events[-1]['returned'] = result
    return result


def click_xy(x, y):
    for _ in range(12):
        qmp('input-send-event', {'events': [
            {'type': 'rel', 'data': {'axis': 'x', 'value': -100}},
            {'type': 'rel', 'data': {'axis': 'y', 'value': -100}}]})
        pump(g, .02)
    for offset in range(0, max(x, y), 80):
        qmp('input-send-event', {'events': [
            {'type': 'rel', 'data': {'axis': 'x', 'value': min(80, max(0, x - offset))}},
            {'type': 'rel', 'data': {'axis': 'y', 'value': min(80, max(0, y - offset))}}]})
        pump(g, .02)
    for down in (True, False):
        qmp('input-send-event', {'events': [
            {'type': 'btn', 'data': {'button': 'left', 'down': down}}]})
        pump(g, .1)


def test_link_hit():
    # Select from what the independent Consumer actually received. The Oracle
    # provides only the window-to-screen origin, not a fabricated target box.
    observed = decode_capture(bytes(g.output))
    reference = observed['oracles'][0]['data']
    window_x, window_y = reference['windowOrigin']
    viewport = reference['viewportInWindow']
    vx, vy, vw, vh = viewport
    nodes = [node for frame in observed['frames'] if frame['direction'] == 'RESP'
             for node in frame['data'].get('nodes', [])]
    selected = next(node for node in nodes if node.get('role') == 'link'
                    and node.get('fragmentsComplete') is True and node.get('visibleFragments'))
    expected = []
    for x, y, w, h in selected['fragments']:
        x0, y0 = max(x, vx), max(y, vy)
        x1, y1 = min(x + w, vx + vw), min(y + h, vy + vh)
        if x1 > x0 and y1 > y0:
            expected.append([x0, y0, x1 - x0, y1 - y0])
    require(expected == selected['visibleFragments'], 'selected link fragment clipping mismatch')
    x, y, w, h = selected['visibleFragments'][0]
    require(w > 0 and h > 0, 'selected link has no interior')
    px, py = x + min(8, (w - 1) // 2) + window_x, y + min(8, (h - 1) // 2) + window_y
    href = selected['href']
    require(':' not in href and '?' not in href and '%' not in href and '\\' not in href,
            'link fixture target outside supported local path syntax')
    target = href.split('#', 1)[0] or reference['document']
    if not target.startswith('/'):
        target = posixpath.join(posixpath.dirname(reference['document']), target)
    target = posixpath.normpath(target)
    require(target in ('/web/ssg.html', '/web/start.html'), 'link target was not prepared by this fixture')
    def resolved_target(node):
        value = node.get('href', '').split('#', 1)[0] or reference['document']
        return posixpath.normpath(value if value.startswith('/') else
                                 posixpath.join(posixpath.dirname(reference['document']), value))
    require(sum(resolved_target(n) == target for n in nodes if n.get('role') == 'link') == 1,
            'navigation target is shared by multiple links; a hit cannot identify the selected link')
    ppm = out / 'link-before.ppm'
    qmp('screendump', {'filename': str(ppm)})
    from PIL import Image
    with Image.open(ppm) as picture:
        screen_width, screen_height = picture.size
        require(0 <= px < screen_width and 0 <= py < screen_height,
                'selected link outside the actual QEMU framebuffer')
        picture.save(out / 'link-before.png')
    ppm.unlink()
    start = len(g.output)
    click_xy(px, py)
    g.expect(('BROWSER_LINK target=' + target).encode(), start=start, timeout=30)
    g.expect(('BROWSER_LOADED path=' + target).encode(), start=start, timeout=30)
    return {'status': 'PASSED_SCOPED', 'scope': 'one visible link after completed paging',
            'consumer_node_id': selected['id'], 'href': href, 'node': selected,
            'screen_point': [px, py], 'window_origin': [window_x, window_y],
            'screen_size': [screen_width, screen_height],
            'viewport_in_window': viewport, 'loaded_target': target,
            'input': 'QEMU input-send-event to guest PS/2; no synthetic widget call',
            'rendered_fragments_global': 'NOT_QUALIFIED', 'screen_occlusion': 'NOT_TESTED',
            'during_paging_interaction': 'NOT_TESTED'}


try:
    if a.require_oracle or a.expect_resource_limit:
        verify_test_receipt()
    with tempfile.TemporaryDirectory(prefix='xos_p2f_') as tmp:
        disk = Path(tmp) / 'work.img'
        create_fat32(disk, 512)
        transfer(disk, 'mkdir', '/bin')
        transfer(disk, 'mkdir', '/web')
        for name, dest in (('session', 'session'), ('consumer', 'ssg-consumer'), ('browser', 'browser')):
            transfer(disk, 'import', '/bin/' + dest + '.elf', inputs[name])
        transfer(disk, 'import', '/web/ssg.html', fixture)
        if a.link_hit:
            target = out / 'link-target.html'
            target.write_text('<html><head><title>Link target</title></head><body><h1>LINK_TARGET_REACHED</h1></body></html>')
            transfer(disk, 'import', '/web/start.html', target)
            report['inputs']['link_target'] = {'path': str(target), 'sha256': sha(target.read_bytes())}
        guest_name = os.path.relpath(out / 'qemu', ROOT / 'build')
        g = Guest(inputs['image'], guest_name, work_disk=disk, iso=image_format == 'iso')
        report['qemu_command'] = g.command
        qemu_path = Path(g.command[0]).resolve(strict=True)
        report['inputs']['qemu'] = {'path': str(qemu_path), 'sha256': sha(qemu_path.read_bytes()),
                                   'version': subprocess.check_output([str(qemu_path), '--version'], text=True).splitlines()[0]}
        g.expect(b'xos64> ', timeout=45)
        send_bytes(g, b'run\r')
        g.expect_supervisor(trace=True, timeout=45)
        command(g, 'demo quiet', b'demo tasks stopped')
        report['baseline'] = resources(g)
        command(g, 'display-start', b'result=0')
        g.expect(b'[display-service] ready')
        report['display'] = resources(g)
        start = len(g.output)
        guest_command = 'exec-driver /bin/session.elf /web/ssg.html browser-pages --browser --text'
        report['guest_command'] = guest_command
        send_bytes(g, (guest_command + '\r').encode())
        g.expect(b'SSG_PAGED_CONSUMER_DONE', start=start, timeout=150)
        if a.link_hit:
            try:
                report['geometry'] = test_link_hit()
            except Exception as error:
                report['geometry'] = {'status': 'FAILED', 'error': repr(error)}
        qmp('input-send-event', {'events': [
            {'type': 'key', 'data': {'down': down, 'key': {'type': 'qcode', 'data': 'esc'}}}
            for down in (True, False)]})
        g.expect(b'SSG_SESSION consumer_wait=', start=start, timeout=60)
        g.expect(b'SSG_SESSION provider_wait=', start=start, timeout=60)
        g.expect_supervisor(start=start, timeout=60)
        report['after'] = resources(g)
        require(report['after'] == report['display'], 'child/pipe resource counters did not return')
        data = bytes(g.output)
        capture = decode_capture(data)
        responses = [f['data'] for f in capture['frames'] if f['direction'] == 'RESP']
        require(responses, 'no Consumer-received IPC responses')
        report['page_node_counts'] = [len(r.get('nodes', [])) for r in responses]
        if a.require_oracle:
            comparison = validate_capture(data, report['inputs']['input']['sha256'])
            (out / 'structure-comparison.json').write_text(json.dumps(comparison, indent=2, ensure_ascii=False) + '\n')
            report['structure'] = {k: v for k, v in comparison.items() if k not in ('comparison', 'frames')}
            report['status'] = comparison['status']
            report['qualification'] = comparison['qualification']
        elif a.expect_resource_limit:
            rejection = validate_resource_rejection(data, report['inputs']['input']['sha256'])
            (out / 'resource-rejection.json').write_text(json.dumps(rejection, indent=2, ensure_ascii=False) + '\n')
            report.update({k: rejection[k] for k in ('status', 'qualification', 'text_limit', 'structure')})
        else:
            require(re.search(rb'^SSG_PAGED_CONSUMER_DONE pages=\d+ nodes=\d+ complete=1 completeness=ORACLE_REQUIRED\r?$', data, re.M),
                    'Consumer did not finish traversal')
            for child in ('consumer', 'provider'):
                require(re.search(rb'^SSG_SESSION ' + child.encode() + rb'_wait=0 outcome=1 code=0\r?$', data, re.M),
                        child + ' did not exit successfully')
            require(all(r.get('status') == 'OK' for r in responses) and responses[-1].get('complete') is True and
                    all(r.get('complete') is False for r in responses[:-1]), 'missing/premature traversal end')
            report['status'] = 'OBSERVED'
        if report['geometry']['status'] == 'FAILED':
            report['status'] = 'FAILED'
except Exception as error:
    report['error'] = repr(error)
    traceback.print_exc()
finally:
    if g:
        data = bytes(g.output)
        (out / 'serial.log').write_bytes(data)
        report['serial_sha256'] = sha(data)
        try:
            capture = decode_capture(data)
            report['frames'], report['oracles'] = [], []
            for kind in ('frames', 'oracles'):
                for record in capture[kind]:
                    direction = record['direction'].lower()
                    name = (f"oracle-{record['sequence']:02d}.json" if kind == 'oracles'
                            else f"{record['sequence']:02d}-{direction}.json")
                    (out / name).write_bytes(record['payload'])
                    saved = {k: record[k] for k in ('sequence', 'direction', 'bytes', 'sha256', 'begin', 'end')}
                    saved['file'] = name
                    if kind == 'frames':
                        wire = struct.pack('<4sII', b'SSG1', len(record['payload']), record['sequence']) + record['payload']
                        wire_name = name.removesuffix('.json') + '.wire'
                        (out / wire_name).write_bytes(wire)
                        saved.update(wire_file=wire_name, wire_sha256=sha(wire),
                                     wire_provenance='header reconstructed from validated protocol fields; payload is exact Consumer log bytes')
                    report[kind].append(saved)
        except Exception as error:
            report['status'] = 'FAILED'
            report['frame_error'] = repr(error)
        g.close()
    report['qemu_command_kind'] = 'template; the runner creates the work disk and QMP socket'
    (out / 'qmp-events.json').write_text(json.dumps(portable(events, public_mappings(), strict=True), indent=2) + '\n')
    (out / 'report.json').write_text(json.dumps(portable(report, public_mappings(), strict=True), indent=2, ensure_ascii=False) + '\n')
if report['status'] not in ('OBSERVED', 'PASSED_SCOPED'):
    sys.exit(1)
