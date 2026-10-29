# SPDX-License-Identifier: Apache-2.0
"""Exercise real dependencies without bypassing LocalPilot security checks."""
import json,sys,os,traceback
sys.path[:0]=['/work/deps','/work/localpilot']
def check(name,fn):
 try:
  detail=fn()
  print('COMPAT:'+json.dumps({'name':name,'status':'PASSED','detail':str(detail)}),flush=True)
 except BaseException as e:
  print('COMPAT:'+json.dumps({'name':name,'status':'FAILED','error':type(e).__name__+': '+str(e)}),flush=True)
def threads():
 import threading
 lock=threading.Lock();values=[]
 def work():
  for i in range(1000):
   with lock:values.append(i)
 a=threading.Thread(target=work);b=threading.Thread(target=work);a.start();b.start();a.join();b.join();assert len(values)==2000
 return '2 native Python threads joined; 2000 locked appends'
def sqlite():
 import sqlite3
 p='/work/sqlite.db';c=sqlite3.connect(p);c.execute('create table if not exists probe(x)');c.execute('insert into probe values (42)');c.commit();c.close()
 c=sqlite3.connect(p);assert c.execute('select max(x) from probe').fetchone()==(42,);assert c.execute('pragma integrity_check').fetchone()==('ok',);c.close();return sqlite3.sqlite_version
def pdf():
 from pypdf import PdfWriter,PdfReader
 import io
 w=PdfWriter();w.add_blank_page(width=72,height=72);b=io.BytesIO();w.write(b);b.seek(0);assert len(PdfReader(b).pages)==1;return 'blank-page write/read; no encrypted/font/image qualification'
def xml():
 from defusedxml.ElementTree import fromstring
 from defusedxml.common import DefusedXmlException
 assert fromstring('<x>42</x>').text=='42'
 try:fromstring('<!DOCTYPE x [<!ENTITY a "x">]><x>&a;</x>')
 except DefusedXmlException:return 'parsed valid XML; entity expansion rejected'
 raise AssertionError('entity expansion was accepted')
def pillow():
 from PIL import Image
 image=Image.new('RGB',(2,2),'red');assert image.getpixel((0,0))==(255,0,0);return 'RGB image'
def psutil():
 import psutil
 p=psutil.Process();return (p.pid,p.create_time(),psutil.virtual_memory().available)
def socket():
 import socket
 with socket.socket() as s:s.bind(('127.0.0.1',0));s.listen(1);return s.getsockname()
def ssl():
 import ssl
 ctx=ssl.create_default_context();assert ctx.check_hostname and ctx.verify_mode==ssl.CERT_REQUIRED;return 'verified context only; no TLS handshake'
def subprocess():
 import subprocess
 p=subprocess.run(['/usr/bin/python3','-c','print(42)'],capture_output=True,text=True,timeout=10,check=True);assert p.stdout.strip()=='42';return 'real child stdout'
def permissions():
 p='/work/private.json';fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);os.write(fd,b'{}');os.close(fd);st=os.stat(p);assert st.st_mode&0o077==0,oct(st.st_mode);return 'owner-only file mode enforced'
def imports(name):
 __import__(name);return 'unmodified upstream module imported; not full service acceptance'
def entropy():
 data=os.urandom(32);assert len(data)==32 and data!=bytes(32);return '32 bytes only; not TLS RNG qualification'
print('COMPAT_ENV:'+json.dumps({'version':sys.version,'platform':sys.platform}),flush=True)
for name,fn in [('threads',threads),('sqlite',sqlite),('pypdf',pdf),('defusedxml',xml),('Pillow',pillow),('psutil',psutil),('socket_loopback',socket),('ssl_verified_context',ssl),('subprocess',subprocess),('file_permissions',permissions),('entropy',entropy)]:check(name,fn)
for module in ['agent.permissions','agent.policy','localpilot_service.security','localpilot_service.server','localpilot_service.cli']:
 check(module,lambda module=module:imports(module))
print('COMPAT_DONE',flush=True)
