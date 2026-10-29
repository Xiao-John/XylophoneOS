# SPDX-License-Identifier: Apache-2.0
"""Controlled loopback HTTP fixture. Host tests are NEVER XOS N2 evidence."""
import argparse,hashlib,http.server,json,secrets,threading,time
from pathlib import Path

class Fixture:
 def __init__(self,output,port=0):
  self.output=Path(output);self.output.mkdir(parents=True,exist_ok=False)
  self.token=secrets.token_hex(16);self.lock=threading.Lock()
  self.body=('<!doctype html><html><head><title>XOS controlled HTTP</title><style>body {background:#eef5fa;color:#17324d;font-size:20px;} h1 {color:#16786a;}</style></head><body><h1>N2 live challenge</h1><p id="challenge">'+self.token+'</p><a href="/probe/'+self.token+'">Live request</a></body></html>').encode()
  fixture=self
  class Handler(http.server.BaseHTTPRequestHandler):
   protocol_version='HTTP/1.1'
   def log_message(self,*args):pass
   def do_GET(self):
    path=self.path
    if path not in ['/'+x+'/'+fixture.token for x in ['probe','redirect','chunked','truncate','slow']]:
     self.send_response(404);self.send_header('Content-Length','0');self.end_headers();return
    mode=path.split('/')[1]
    if mode=='slow':time.sleep(.2)
    if mode=='redirect':
     self.send_response(302);self.send_header('Location','/probe/'+fixture.token);self.send_header('Content-Length','0');self.end_headers();return
    body=fixture.body
    self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('X-XOS-SHA256',hashlib.sha256(body).hexdigest())
    if mode=='chunked':self.send_header('Transfer-Encoding','chunked')
    else:self.send_header('Content-Length',str(len(body)+(8 if mode=='truncate' else 0)))
    self.send_header('Connection','close');self.end_headers()
    if mode=='chunked':
     for chunk in [body[:71],body[71:]]:self.wfile.write(f'{len(chunk):x}\r\n'.encode()+chunk+b'\r\n')
     self.wfile.write(b'0\r\n\r\n')
    else:self.wfile.write(body)
    self.wfile.flush();self.close_connection=True
    record={'time_ns':time.time_ns(),'peer':self.client_address,'path':path,'mode':mode,'body_sha256':hashlib.sha256(body).hexdigest(),'body_bytes':len(body),'scope':'host fixture log; guest origin must be independently proven'}
    with fixture.lock:
     with (fixture.output/'requests.jsonl').open('a') as f:f.write(json.dumps(record)+'\n')
  self.server=http.server.ThreadingHTTPServer(('127.0.0.1',port),Handler);self.server.daemon_threads=True
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
  self.receipt={'scope':'HOST_FIXTURE_ONLY; N2 BLOCKED until lawful bridge','host':'127.0.0.1','port':self.server.server_port,'guest_host':'10.0.2.2','token':self.token,'path':'/probe/'+self.token,'body_sha256':hashlib.sha256(self.body).hexdigest(),'tls':'NOT_RUN'}
  (self.output/'fixture.json').write_text(json.dumps(self.receipt,indent=2)+'\n')
 def start(self):self.thread.start()
 def close(self):self.server.shutdown();self.server.server_close();self.thread.join()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--port',type=int,default=18080);a=p.parse_args();f=Fixture(a.output,a.port);f.start();print(json.dumps(f.receipt),flush=True)
 try:f.thread.join()
 except KeyboardInterrupt:f.close()
if __name__=='__main__':main()
