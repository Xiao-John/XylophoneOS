#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise the production bounded HTTPS fetcher with a real native net2 guest."""
import argparse
from hashlib import file_digest,sha256
import json
from pathlib import Path
import re
import secrets
import socket
import ssl
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from native_tls_guest import prepare
from process_smoke import command,resources
from task_smoke import pump,send_bytes
from work_disk import transfer


def digest(path):
    with path.open('rb') as stream: return file_digest(stream,'sha256').hexdigest()


def exchange(guest,service,scenario,certificates,policy):
    certificate=scenario if scenario in ('wrong-host','unknown-ca','expired') else 'valid'
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version=context.maximum_version=ssl.TLSVersion.TLSv1_3
    context.num_tickets=0
    chain=certificates/(certificate+'-chain.pem')
    context.load_cert_chain(chain,certificates/(certificate+'.key'))
    server={'application_request':False};stop=threading.Event()
    context.set_servername_callback(lambda connection,name,selected:server.update(sni=name))
    nonce=secrets.token_hex(16)
    expected=(f"GET /{nonce} HTTP/1.1\r\nHost: {policy['host']}:{policy['port']}\r\n"
              'Connection: close\r\nAccept-Encoding: identity\r\n\r\n').encode()
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        listener.bind(('127.0.0.1',policy['port']));listener.listen(1);listener.settimeout(30)
        def serve():
            try:
                connection,_=listener.accept()
                with connection:
                    connection.settimeout(20)
                    try: stream=context.wrap_socket(connection,server_side=True)
                    except ssl.SSLError as error:
                        server['handshake_alert']=error.reason;return
                    with stream:
                        server['version']=stream.version();server['cipher']=stream.cipher()[0]
                        request=bytearray()
                        while b'\r\n\r\n' not in request and len(request)<=512:
                            part=stream.recv(512)
                            if not part: break
                            request.extend(part)
                        server['application_request']=bool(request)
                        if bytes(request)!=expected: raise AssertionError('unexpected decrypted HTTP request')
                        header=b'HTTP/1.1 200 OK\r\nContent-Length: 32\r\nConnection: close\r\n\r\n'
                        stream.sendall(header[:13]);stream.sendall(header[13:]+nonce[:11].encode())
                        stream.sendall(nonce[11:].encode())
                        if scenario=='truncated':
                            stream.shutdown(socket.SHUT_WR);server['abrupt_transport_eof']=True
                        elif scenario=='server-close':
                            stream.unwrap().close();server['client_close_notify']=True
                        else:
                            # Content-Length completed before close_notify. Force the
                            # guest's first SSL_shutdown to send, then wait for its
                            # second call to consume our authenticated response.
                            if stream.recv(1)!=b'': raise AssertionError('unexpected post-response application data')
                            server['client_close_notify']=True
                            if scenario=='stall':
                                server['withheld_close_notify']=True
                                if not stop.wait(20): raise AssertionError('guest did not enforce its shutdown deadline')
                            else:
                                stream.unwrap().close();server['peer_close_notify']=True
            except Exception as error: server['error']=str(error)
        worker=threading.Thread(target=serve,daemon=True);worker.start()
        before=int(time.time())
        try:
            row=command(guest,f'exec-file /clarke_https.elf {service} {scenario} {nonce}',
                        b'kind=exited code=',timeout=40)
        finally:
            stop.set();worker.join(timeout=5)
        after=int(time.time())
        if worker.is_alive(): raise AssertionError('TLS peer did not finish')
    match=re.search(rb'CLARKE_HTTPS scenario=([^ ]+) result=(-?\d+) status=(\d+) bytes=(\d+) '
                    rb'elapsed_ns=(\d+) realtime=(\d+) pass=(\d+)',row)
    if not match or match[1].decode()!=scenario or match[7]!=b'1' or b'kind=exited code=0' not in row or 'error' in server:
        raise AssertionError(f'{scenario}: guest/peer failed: {row!r} / {server}')
    realtime=int(match[6])
    if not before-2<=realtime<=after+2: raise AssertionError('guest certificate clock differs from controlled host')
    if server.get('sni')!=policy['host']: raise AssertionError('HTTPS SNI differs from the pinned origin')
    if scenario in ('wrong-host','unknown-ca','expired'):
        if server['application_request'] or not server.get('handshake_alert'):
            raise AssertionError('certificate refusal did not precede application data')
    else:
        if not server['application_request'] or server.get('version')!='TLSv1.3':
            raise AssertionError('missing actual TLS application exchange')
        if scenario!='truncated' and not server.get('client_close_notify'):
            raise AssertionError('guest did not send its authenticated close')
    return {'scenario':scenario,'result':int(match[2]),'status':int(match[3]),'bytes':int(match[4]),
            'elapsed_ns':int(match[5]),'guest_realtime':realtime,'host_realtime_window':[before,after],
            'peer_chain_sha256':digest(chain),'nonce_sha256':sha256(nonce.encode()).hexdigest(),**server}


def test(args):
    probe=json.loads((args.probe/'manifest.json').read_bytes())
    system=json.loads((args.system/'manifest.json').read_bytes())
    certificates=json.loads((args.certificates/'certificates.json').read_bytes())
    policy=probe['policy'];elf=args.probe/'https_probe.elf';image=args.system/'xos-install.iso'
    if probe['status']!='linked' or digest(elf)!=probe['elf_sha256'] or policy['ipv4_address']!='10.0.2.2':
        raise ValueError('invalid controlled HTTPS probe identity')
    if digest(args.certificates/'clarke-root.der')!=policy['ca_sha256'] or policy['host']!='tls.xos.test':
        raise ValueError('probe trust anchor/origin differs from the certificate fixture')
    for name,expected in probe['inputs'].items():
        if digest(ROOT/name)!=expected: raise ValueError('probe input changed: '+name)
    for name,expected in certificates['public_fixtures'].items():
        if digest(args.certificates/name)!=expected: raise ValueError('certificate changed: '+name)
    for name in ('src/shared/include/xos/net_service_abi.hpp','src/user/include/xos/net_service_client.hpp'):
        if probe['inputs'][name]!=system['sources'][name]: raise ValueError('probe/native net2 input mismatch')
    if digest(image)!=system['artifacts'][image.name]['sha256']: raise ValueError('native system image changed')
    args.output.mkdir(parents=True,exist_ok=False)
    disk=args.output/'https.img';create_fat32(disk,512);transfer(disk,'import','/clarke_https.elf',elf)
    readback=args.output/'readback.elf';transfer(disk,'export','/clarke_https.elf',readback)
    if digest(readback)!=probe['elf_sha256']: raise ValueError('guest payload differs after import')
    readback.unlink()
    report={'status':'failed','system_manifest_sha256':digest(args.system/'manifest.json'),
        'probe_manifest_sha256':digest(args.probe/'manifest.json'),'image_sha256':digest(image),
        'elf_sha256':probe['elf_sha256'],'runner_sha256':digest(Path(__file__)),
        'sdk_manifest_sha256':probe['sdk_manifest_sha256'],'policy':policy,'cases':[]}
    guest=None
    try:
        guest=Guest(image,'clarke_https',work_disk=disk,network=True,log_dir=args.output,qmp_enabled=False)
        guest.expect(b'xos64> ',timeout=30);send_bytes(guest,b'run\r');guest.expect_supervisor(trace=True,timeout=30)
        command(guest,'demo quiet',b'demo tasks')
        if b'[net-start] pid=' in guest.output: command(guest,'net-stop',b'[wait] pid=',timeout=30)
        before=resources(guest)
        row=command(guest,'net-start 41',b'[net-start] pid=',timeout=60)
        guest.expect(b'[net] ready native_v2=1',timeout=60)
        service=int(re.search(rb'\[net-start\] pid=(\d+)',row)[1]);baseline=resources(guest)
        for scenario in ('valid','server-close','stall','truncated','wrong-host','unknown-ca','expired','valid'):
            report['cases'].append(exchange(guest,service,scenario,args.certificates,policy))
            for _ in range(30):
                current=resources(guest)
                if current==baseline: break
                pump(guest,0.1)
            if current!=baseline: raise AssertionError(f'{scenario}: process/IPC resources did not return')
        command(guest,'net-stop',b'[wait] pid=',timeout=30)
        for _ in range(30):
            after=resources(guest)
            if after==before: break
            pump(guest,0.1)
        if after!=before: raise AssertionError('network teardown leaked resources')
        report.update(status='passed',before_service=before,after_service=after,exchange_baseline=baseline)
    finally:
        if guest:
            guest.close();(args.output/'guest.serial.log').write_bytes(guest.output)
        disk.unlink(missing_ok=True)
        (args.output/'report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
        files={path.name:digest(path) for path in args.output.iterdir() if path.is_file() and path.name!='manifest.json'}
        (args.output/'manifest.json').write_text(json.dumps({'version':1,'files':files},indent=2,sort_keys=True)+'\n')
    print(report['status'])


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='mode',required=True)
    preparation=sub.add_parser('prepare');preparation.add_argument('--certificates',required=True,type=lambda value:Path(value).resolve())
    check=sub.add_parser('test')
    for name in ('system','probe','certificates','output'):
        check.add_argument('--'+name,required=True,type=lambda value:Path(value).resolve())
    args=parser.parse_args()
    if args.mode=='prepare':
        prepare(args.certificates)
        (args.certificates/'clarke-root.der').write_bytes(ssl.PEM_cert_to_DER_cert((args.certificates/'root.pem').read_text()))
    else: test(args)


if __name__=='__main__': main()
