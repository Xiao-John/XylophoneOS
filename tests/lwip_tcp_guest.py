#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Controlled lwIP TCP guest/host exchange; static QEMU IPv4 profile only."""
import argparse
import hashlib
import json
import secrets
import socket
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import send_bytes, pump
from work_disk import transfer
from xos_app import tree_receipt


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', type=Path, required=True)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    system, payload, out = args.system.resolve(), args.payload.resolve(), args.output.resolve()
    out.relative_to(ROOT / 'build')
    out.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((system / 'manifest.json').read_text())
    receipt_path = payload.with_name('tcp_probe.receipt.json')
    receipt = json.loads(receipt_path.read_text())
    if (receipt['binary_sha256'] != sha(payload) or
        receipt['source_sha256'] != sha(ROOT/'src/ports/lwip/net_tcp_probe.cpp') or
        receipt['builder_sha256'] != sha(ROOT/'scripts/build_lwip_tcp_probe.py') or
        receipt['sdk_tree_sha256'] != tree_receipt(system/'sdk')[0] or
        receipt['lwip_library_sha256'] != sha(payload.parent/'port/tree/usr/lib/liblwip.a')):
        raise ValueError('probe build receipt mismatch')
    for name, digest in manifest['sources'].items():
        if sha(ROOT / name) != digest: raise ValueError('source mismatch: '+name)
    for name, entry in manifest['artifacts'].items():
        if sha(system / name) != entry['sha256']: raise ValueError('artifact mismatch: '+name)
    challenge = secrets.token_bytes(32)
    server = socket.socket(); server.bind(('127.0.0.1', 0)); server.listen(1); server.settimeout(45)
    port = server.getsockname()[1]
    result = {'status': 'failed', 'build_id': manifest['build_id'], 'image_sha256': sha(system/'xos-install.iso'),
              'payload_sha256': sha(payload), 'source_sha256': sha(ROOT/'src/ports/lwip/net_tcp_probe.cpp'),
              'build_receipt_sha256': sha(receipt_path), 'sdk_tree_sha256': receipt['sdk_tree_sha256'],
              'lwip_archive_sha256': receipt['archive_sha256'],
              'challenge_sha256': hashlib.sha256(challenge).hexdigest(), 'checks': [],
              'not_run': ['UDP','DNS','DHCP','TLS','production entropy','multi_client','packet_loss_reordering']}
    host = {}; guest = None
    def serve():
        try:
            conn, _ = server.accept()
            with conn:
                conn.settimeout(20); data=b''
                while len(data)<17:
                    part=conn.recv(17-len(data))
                    if not part: break
                    data+=part
                host['request']=data.decode('ascii',errors='replace')
                if data != b'XOS-TCP-PROBE-v1\n': raise ValueError('incorrect guest request')
                conn.sendall(challenge[:7]); conn.sendall(challenge[7:]); conn.shutdown(socket.SHUT_WR)
                host['client_eof'] = conn.recv(1) == b''
        except Exception as error: host['error']=str(error)
    worker=threading.Thread(target=serve,daemon=True); worker.start()
    try:
        with tempfile.TemporaryDirectory(prefix='xos_tcp_guest_') as temp:
            disk=Path(temp)/'work.img'; create_fat32(disk,512); transfer(disk,'mkdir','/bin'); transfer(disk,'import','/bin/tcp.elf',payload)
            guest=Guest(system/'xos-install.iso',str(out.relative_to(ROOT/'build'))+'/guest',iso=True,network=True,work_disk=disk)
            result['qemu_command']=guest.command
            guest.expect(b'xos64> ',timeout=60); send_bytes(guest,b'run\r'); guest.expect_supervisor(trace=True,timeout=60)
            command(guest,'demo quiet',b'demo tasks'); pump(guest,.2)
            output=command(guest,'net-start 41',b'[net-start] pid=',timeout=60)
            guest.expect(b'[net] ready',timeout=60); baseline=resources(guest)
            output=command(guest,f'exec-driver /bin/tcp.elf {port}',b'kind=exited code=',timeout=90)
            expected=('TCP_REPLY:'+challenge.hex()).encode()
            if expected not in output or b'TCP_GUEST_PASS' not in output or b'kind=exited code=0' not in output: raise AssertionError(output[-4000:])
            worker.join(timeout=20)
            if worker.is_alive() or host.get('error') or not host.get('client_eof'): raise AssertionError(str(host))
            if resources(guest)!=baseline: raise AssertionError('probe did not reclaim resources')
            result['checks']=['host_request_verified','fresh_32_byte_challenge_exact','host_and_guest_close','probe_resources_restored']
            closed = socket.socket(); closed.bind(('127.0.0.1', 0)); closed_port = closed.getsockname()[1]; closed.close()
            rejected = command(guest, f'exec-driver /bin/tcp.elf {closed_port}', b'kind=exited code=', timeout=90)
            if b'TCP_GUEST_FAIL' not in rejected or b'kind=exited code=1' not in rejected:
                raise AssertionError(rejected[-4000:])
            if resources(guest) != baseline: raise AssertionError('failed connection did not reclaim resources')
            result['checks'].append('closed_port_fails_and_reclaims_resources')
            stopped = command(guest,'net-stop',b'kind=exited code=',timeout=60)
            if b'[net] close=0' not in stopped or b'kind=exited code=0' not in stopped:
                raise AssertionError(stopped[-4000:])
            result['checks'].append('network_service_reset_close')
            result['host']=host; result['status']='passed'
    except Exception as error:
        result['error']=str(error); raise
    finally:
        server.close()
        if guest:
            (out/'guest.serial.log').write_bytes(guest.output); guest.close()
        (out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS lwIP controlled TCP guest')

if __name__ == '__main__': main()
