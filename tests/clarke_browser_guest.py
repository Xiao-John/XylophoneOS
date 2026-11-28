#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Actual WebCore/Qt scanout, native network isolation and browser lifetimes."""
import argparse
from hashlib import file_digest,sha256
import json
from pathlib import Path
import queue
import re
import socket
import socketserver
import ssl
import sys
import threading

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import command,resources
from task_smoke import pump,send_bytes
from work_disk import transfer


def digest(path):
    with path.open('rb') as stream:return file_digest(stream,'sha256').hexdigest()


def ppm(path):
    with path.open('rb') as stream:
        if stream.readline().strip()!=b'P6':raise ValueError('expected binary RGB PPM')
        line=stream.readline()
        while line.startswith(b'#'):line=stream.readline()
        width,height=map(int,line.split())
        if stream.readline().strip()!=b'255':raise ValueError('unsupported PPM depth')
        pixels=stream.read()
    if len(pixels)!=width*height*3:raise ValueError('truncated PPM')
    return width,height,pixels


def stroke(guest,key):
    for down in (True,False):guest.qmp('input-send-event',{'events':[{'type':'key','data':{'down':down,'key':{'type':'qcode','data':key}}}]})
    pump(guest,0.08)


def chord(guest,modifier,key):
    guest.qmp('input-send-event',{'events':[{'type':'key','data':{'down':True,'key':{'type':'qcode','data':modifier}}}]})
    stroke(guest,key)
    guest.qmp('input-send-event',{'events':[{'type':'key','data':{'down':False,'key':{'type':'qcode','data':modifier}}}]})
    pump(guest,0.08)


def address(guest,url):
    chord(guest,'ctrl','a');stroke(guest,'backspace')
    punctuation={':':('semicolon',True),'/':('slash',False),'.':('dot',False),'-':('minus',False)}
    for letter in url:
        if letter.isascii() and letter.isalnum():stroke(guest,letter)
        else:
            key,shift=punctuation[letter]
            chord(guest,'shift',key) if shift else stroke(guest,key)
    stroke(guest,'ret')


class http_peer:
    def __init__(self):
        self.pending=queue.Queue();self.records=[];owner=self
        class server(socketserver.ThreadingTCPServer):
            allow_reuse_address=True;daemon_threads=True
        class handler(socketserver.BaseRequestHandler):
            def handle(self):
                item=owner.pending.get(timeout=30);connection=self.request;connection.settimeout(15)
                try:
                    request=bytearray()
                    while b'\r\n\r\n' not in request and len(request)<8192:
                        part=connection.recv(1024)
                        if not part:break
                        request.extend(part)
                    expected=f'GET /fixture.html HTTP/1.1\r\nHost: 10.0.2.2:{owner.port}\r\n'.encode()
                    if not request.startswith(expected) or not request.endswith(b'Connection: close\r\nAccept-Encoding: identity\r\n\r\n'):
                        raise AssertionError('unexpected native browser HTTP request')
                    item['record']['request_sha256']=sha256(request).hexdigest();item['received'].set()
                    if item['mode']=='hold':
                        if not item['released'].wait(20):raise AssertionError('cancel did not finish before peer deadline')
                        item['record']['cancelled_request']=True;return
                    body=item['body'];declared=len(body)+(1 if item['mode']=='truncated' else 0)
                    header=f'HTTP/1.1 200 OK\r\nContent-Length: {declared}\r\nConnection: close\r\n\r\n'.encode()
                    connection.sendall(header[:17]);connection.sendall(header[17:]+body)
                    connection.shutdown(socket.SHUT_WR);item['record']['response_bytes']=len(body)
                except Exception as error:item['record']['error']=str(error);item['received'].set()
                finally:item['finished'].set()
        self.server=server(('127.0.0.1',0),handler);self.port=self.server.server_address[1]
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def add(self,label,body,mode='normal'):
        record={'label':label,'mode':mode,'body_sha256':sha256(body).hexdigest()};self.records.append(record)
        item={'record':record,'body':body,'mode':mode,'received':threading.Event(),
              'released':threading.Event(),'finished':threading.Event()}
        self.pending.put(item);return item
    def finish(self,item):
        item['released'].set()
        if not item['finished'].wait(5) or 'error' in item['record']:raise AssertionError('HTTP peer failed: '+repr(item['record']))
    def close(self):
        self.server.shutdown();self.server.server_close();self.thread.join(5)


def completed(guest,navigation,start,result=0):
    prefix=f'CLARKE_NAVIGATION_DONE navigation={navigation} result={result} '.encode()
    found=guest.expect_any((prefix,b'CLARKE_SESSION_FAILED'),start=start,timeout=120)
    if found!=prefix:raise AssertionError('browser controller failed: '+repr(bytes(guest.output)[start:]))
    guest.expect(b'free_pages=',start=start,timeout=10);pump(guest,0.1)
    row=bytes(guest.output)[start:]
    match=re.search(rb'CLARKE_NAVIGATION_DONE navigation='+str(navigation).encode()+
        rb' result=(-?\d+) lifetimes_reaped=(\d+) revoked=(\d+) free_pages=(\d+)',row)
    if not match or tuple(map(int,match.groups()[:3]))!=(result,1,0):raise AssertionError('navigation did not restore policy/process capacity')
    if result in (0,-5):
        raw=re.findall(rb'CLARKE_RENDERER_RAW_NET connect=(-?\d+) request=(-?\d+)',row)
        if len(raw)!=1 or int(raw[0][1]) not in (-202,-206):raise AssertionError('renderer raw net2 was not actually denied')
        if f'CLARKE_BROKER_POLICY navigation={navigation} live=0 release=-202'.encode() not in row:
            raise AssertionError('live ordinary broker or unauthorized release control failed')
    presented=re.findall(rb'CLARKE_VIEWPORT_PRESENT navigation='+str(navigation).encode()+
        rb' x=(\d+) y=(\d+) width=320 height=180 frame=(\d+) sha256=([0-9a-f]{64})',row)
    if len(presented)!=(1 if result==0 else 0):raise AssertionError('unexpected viewport frame acknowledgement')
    prepared=[{'role':int(role),'pid':int(pid),'domain':int(domain),'pages':int(pages),'threads':int(threads),'revoked':int(revoked)}
        for role,pid,domain,pages,threads,revoked in re.findall(rb'CLARKE_PREPARED navigation='+str(navigation).encode()+
        rb' role=(\d+) pid=(\d+) domain=(\d+) pages=(\d+) threads=(\d+) revoked=(\d+)',row)]
    return {'navigation':navigation,'result':result,'free_pages':int(match[4]),'prepared':prepared,
            'presentation':[value.decode() for value in presented[0]] if presented else None}


def capture(guest,record,reference,output):
    x,y,serial,rgba_hash=record['presentation'];x=int(x);y=int(y)
    path=output/f"navigation-{record['navigation']:02}.ppm"
    guest.qmp('screendump',{'filename':str(path)})
    width,height,pixels=ppm(path);rw,rh,expected=ppm(reference)
    if (width,height)!=(800,600) or (rw,rh)!=(320,180) or x+rw>width or y+rh>height:
        raise AssertionError('unexpected actual Qt scanout geometry')
    actual=b''.join(pixels[((y+row)*width+x)*3:((y+row)*width+x+rw)*3] for row in range(rh))
    if actual!=expected:raise AssertionError('Qt scanout does not equal independently executed WebCore paint')
    rgba=b''.join(expected[index:index+3]+b'\xff' for index in range(0,len(expected),3))
    if sha256(rgba).hexdigest()!=rgba_hash:raise AssertionError('IPC frame hash differs from actual WebCore pixels')
    record['scanout']={'file':path.name,'sha256':digest(path),'reference_sha256':digest(reference),
                       'exact_pixels':True,'frame_serial':int(serial),'x':x,'y':y}


def https_peer(certificates,policy,body):
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.minimum_version=ssl.TLSVersion.TLSv1_3;context.num_tickets=0
    context.load_cert_chain(certificates/'valid-chain.pem',certificates/'valid.key')
    state={};context.set_servername_callback(lambda connection,name,selected:state.update(sni=name))
    listener=socket.socket();listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    listener.bind(('127.0.0.1',policy['port']));listener.listen(1);listener.settimeout(30)
    def serve():
        try:
            connection,_=listener.accept()
            with connection:
                connection.settimeout(15)
                with context.wrap_socket(connection,server_side=True,suppress_ragged_eofs=False) as stream:
                    request=bytearray()
                    while b'\r\n\r\n' not in request and len(request)<4096:
                        part=stream.recv(1024)
                        if not part:break
                        request.extend(part)
                    if not request.startswith(f"GET /fixture.html HTTP/1.1\r\nHost: {policy['host']}:{policy['port']}\r\n".encode()):
                        raise AssertionError('unexpected HTTPS browser request')
                    state['request_sha256']=sha256(request).hexdigest();state['version']=stream.version()
                    stream.sendall(f'HTTP/1.1 200 OK\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n'.encode()+body)
                    if stream.recv(1)!=b'':raise AssertionError('missing client TLS close notification')
                    stream.unwrap().close();state['bidirectional_close_notify']=True
        except Exception as error:state['error']=str(error)
        finally:listener.close()
    worker=threading.Thread(target=serve,daemon=True);worker.start();return worker,state


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('system','bundle','dom-results','certificates','output'):
        parser.add_argument('--'+name,required=True,type=lambda value:Path(value).resolve())
    parser.add_argument('--mode',choices=('normal','fault'),default='normal');args=parser.parse_args()
    system=json.loads((args.system/'manifest.json').read_bytes());bundle=json.loads((args.bundle/'manifest.json').read_bytes())
    dom=json.loads((args.dom_results/'report.json').read_bytes());selected=system['clarke']
    if bundle['status']!='clarke_webcore_browser_linked' or selected['bundle_manifest_sha256']!=digest(args.bundle/'manifest.json'):
        raise ValueError('system does not pin this complete browser bundle')
    parent=bundle.get('parent_bundle_manifest_sha256',digest(args.bundle/'manifest.json'))
    if dom['status']!='passed' or dom['bundle_manifest_sha256']!=parent:raise ValueError('DOM pixel baseline belongs to another browser')
    fault=bundle.get('test_profile',{}).get('renderer_fault_navigation',0)
    if fault!=(2 if args.mode=='fault' else 0):raise ValueError('incorrect isolated renderer fault profile')
    image=args.system/'xos-install.iso'
    if digest(image)!=system['artifacts'][image.name]['sha256']:raise ValueError('native image changed')
    for name in ('src/user/programs/clarke_session.hpp','src/user/include/xos/execution.hpp','src/user/loader/load.cpp',
                 'src/shared/include/xos/net_service_abi.hpp','src/user/network/service_core.cpp',
                 'src/kernel/platform/pc/pci.cpp','src/kernel/arch/x86_64/paging.cpp'):
        if digest(ROOT/name)!=system['sources'][name]:raise ValueError('qualified system source changed: '+name)
    args.output.mkdir(parents=True,exist_ok=False);disk=args.output/'browser.img';create_fat32(disk,512)
    for directory in ('/usr','/usr/bin','/usr/libexec','/usr/libexec/clarke','/usr/share','/usr/share/fonts','/usr/share/fonts/clarke'):
        transfer(disk,'mkdir',directory)
    for destination,item in selected['files'].items():
        path=args.bundle/item['artifact']
        if digest(path)!=item['sha256']:raise ValueError('browser artifact changed: '+item['artifact'])
        transfer(disk,'import',destination,path)
        readback=args.output/'readback';transfer(disk,'export',destination,readback)
        if digest(readback)!=item['sha256']:raise ValueError('browser disk import changed bytes')
        readback.unlink()
    fixtures=ROOT/'tests/fixtures/webkit/dom_css';names=('box','flex','grid','cascade','clip','text')
    bodies={name:(fixtures/(name+'.html')).read_bytes() for name in names}
    for name in names:
        if digest(args.dom_results/(name+'.ppm'))!=dom['ppm'][name]['sha256']:raise ValueError('DOM reference image changed')
    report={'status':'failed','mode':args.mode,'runner_sha256':digest(Path(__file__)),
        'bundle_manifest_sha256':digest(args.bundle/'manifest.json'),'system_manifest_sha256':digest(args.system/'manifest.json'),
        'dom_report_sha256':digest(args.dom_results/'report.json'),'image_sha256':digest(image),'navigations':[]}
    guest=None;peer=http_peer()
    try:
        guest=Guest(image,'clarke_browser',work_disk=disk,network=True,log_dir=args.output)
        guest.expect(b'xos64> ',timeout=60);send_bytes(guest,b'run\r');guest.expect_supervisor(trace=True,timeout=60)
        command(guest,'demo quiet',b'demo tasks')
        if b'[net-start] pid=' in guest.output:command(guest,'net-stop',b'[wait] pid=',timeout=30)
        cold=resources(guest)
        for cycle in range(2):
            start=len(guest.output);command(guest,'net-start 41',b'[net-start] pid=',timeout=60)
            guest.expect(b'[net] ready native_v2=1',start=start,timeout=60);command(guest,'net-stop',b'[wait] pid=',timeout=30)
            current=resources(guest)
            if cycle==0:
                initialized=current
                if cold[1:]!=current[1:] or cold[0]-current[0] not in (0,1):raise AssertionError('unexpected cold device observer allocation')
            elif current!=initialized:raise AssertionError('plain device lifecycle is not stable')
        report['device_initialization']={'cold':cold,'initialized':initialized,'second_plain_cycle':current}
        start=len(guest.output);command(guest,'net-start 41',b'[net-start] pid=',timeout=60)
        guest.expect(b'[net] ready native_v2=1',start=start,timeout=60)
        start=len(guest.output);row=command(guest,'interactium-start',b'[interactium-start] pid=',timeout=120)
        guest.expect(b'[interactium-service] ready',start=start,timeout=120)
        display=int(re.search(rb'\[display-start\] pid=(\d+)',row)[1]);compositor=int(re.search(rb'\[interactium-start\] pid=(\d+)',row)[1])
        baseline=resources(guest);report['before_browser']=baseline
        for _ in range(3):guest.qmp('input-send-event',{'events':[{'type':'rel','data':{'axis':'x','value':-500}},{'type':'rel','data':{'axis':'y','value':-500}}]})
        initial=peer.add('navigation-1',bodies['box']);begin=len(guest.output)
        send_bytes(guest,f'clarke-check http://10.0.2.2:{peer.port}/fixture.html\r'.encode())
        guest.expect(b'CLARKE_SESSION_READY ui=',start=begin,timeout=120)
        record=completed(guest,1,begin);capture(guest,record,args.dom_results/'box.ppm',args.output)
        report['navigations'].append(record);peer.finish(initial)
        for navigation in range(2,4 if args.mode=='fault' else 21):
            name=names[(navigation-1)%len(names)];item=peer.add(f'navigation-{navigation}',bodies[name]);start=len(guest.output)
            stroke(guest,'f5');result=-5 if args.mode=='fault' and navigation==2 else 0
            record=completed(guest,navigation,start,result);peer.finish(item)
            if not result:capture(guest,record,args.dom_results/(name+'.ppm'),args.output)
            elif b'CLARKE_RENDERER_INJECTED_FAULT navigation=2' not in bytes(guest.output)[start:]:raise AssertionError('missing real renderer trap')
            report['navigations'].append(record)
        if args.mode=='normal':
            item=peer.add('cancel',bodies['box'],'hold');start=len(guest.output);stroke(guest,'f5')
            if not item['received'].wait(10):raise AssertionError('cancel fixture never reached the real network')
            stroke(guest,'esc');report['navigations'].append(completed(guest,21,start,-1));peer.finish(item)
            for navigation,name,mode,result in ((22,'flex','normal',0),(23,'box','truncated',-4),(24,'grid','normal',0)):
                item=peer.add(f'navigation-{navigation}',bodies[name],mode);start=len(guest.output);stroke(guest,'f5')
                record=completed(guest,navigation,start,result);peer.finish(item)
                if not result:capture(guest,record,args.dom_results/(name+'.ppm'),args.output)
                report['navigations'].append(record)
            policy=bundle['network_policy']['https']
            if digest(args.certificates/'clarke-root.der')!=policy['ca_sha256']:raise ValueError('HTTPS fixture trust anchor changed')
            worker,tls=https_peer(args.certificates,policy,bodies['text']);start=len(guest.output)
            address(guest,policy['origin']+'/fixture.html');record=completed(guest,25,start)
            worker.join(5)
            if worker.is_alive() or 'error' in tls or not tls.get('bidirectional_close_notify') or tls.get('sni')!=policy['host']:
                raise AssertionError('full browser HTTPS peer failed: '+repr(tls))
            capture(guest,record,args.dom_results/'text.ppm',args.output);report['navigations'].append(record);report['https']=tls
        ending=len(guest.output);chord(guest,'ctrl','q')
        event=guest.expect_any((b'CLARKE_SESSION_RELEASED',b'CLARKE_SESSION_FAILED'),start=ending,timeout=120)
        if event!=b'CLARKE_SESSION_RELEASED':raise AssertionError('browser did not reap all owned children')
        guest.expect_supervisor(start=ending,timeout=30)
        if resources(guest)!=baseline or b'restored=1' not in bytes(guest.output)[ending:]:raise AssertionError('browser resources did not return exactly')
        command(guest,f'kill {compositor}',b'kill: accepted');command(guest,f'wait {compositor}',b'kind=killed',timeout=60)
        command(guest,'exec gfxdemo stop',b'kind=exited code=0',timeout=60);command(guest,f'wait {display}',b'kind=exited code=0',timeout=60)
        command(guest,'net-stop',b'[wait] pid=',timeout=30);after=resources(guest)
        if after!=initialized:raise AssertionError('display/network service teardown changed initialized resources')
        renderer_pids=[item['pid'] for row in report['navigations'] for item in row['prepared'] if item['role']==3]
        if len(renderer_pids)!=len(set(renderer_pids)):raise AssertionError('renderer lifetime PID reused')
        report.update(status='passed',after_services=after,renderer_pids=renderer_pids)
    except BaseException as error:report['error']=str(error);raise
    finally:
        peer.close();report['http_peer']=peer.records
        if guest:guest.close();(args.output/'guest.serial.log').write_bytes(guest.output)
        disk.unlink(missing_ok=True)
        (args.output/'report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
        files={path.name:digest(path) for path in args.output.iterdir() if path.is_file() and path.name!='manifest.json'}
        (args.output/'manifest.json').write_text(json.dumps({'version':1,'files':files},indent=2,sort_keys=True)+'\n')
    print(report['status'])


if __name__=='__main__':main()
