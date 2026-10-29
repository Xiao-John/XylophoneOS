# SPDX-License-Identifier: Apache-2.0
"""Verify fixture HTTP bytes/errors with a HOST client; not guest networking."""
import argparse,hashlib,http.client,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from modern_apps_http_fixture import Fixture

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();f=Fixture(a.output);f.start();rows=[]
 try:
  for mode in ['probe','chunked','slow','redirect','truncate']:
   c=http.client.HTTPConnection('127.0.0.1',f.server.server_port,timeout=3);c.request('GET','/'+mode+'/'+f.token);r=c.getresponse()
   try:
    data=r.read();passed=(r.status==302 and r.getheader('Location')=='/probe/'+f.token) if mode=='redirect' else data==f.body and r.getheader('X-XOS-SHA256')==hashlib.sha256(data).hexdigest()
    if mode=='truncate':passed=False
   except http.client.IncompleteRead as e:passed=mode=='truncate' and e.partial==f.body
   rows.append({'name':mode,'status':'PASSED' if passed else 'FAILED','execution':'HOST_LOOPBACK_ONLY'});c.close()
 finally:f.close()
 report={'scope':'host fixture qualification only','N2':'BLOCKED','checks':rows};(a.output/'test.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(any(x['status']!='PASSED' for x in rows))
if __name__=='__main__':main()
