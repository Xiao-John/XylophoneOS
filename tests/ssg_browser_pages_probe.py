import sys,tempfile,json,traceback,hashlib
from pathlib import Path
ROOT=Path.cwd();sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'scripts')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from work_disk import transfer
from process_smoke import command,resources
from task_smoke import send_bytes,pump
out=ROOT/'build/p2d-guest';out.mkdir(exist_ok=True);g=None; report={'status':'FAILED'}
try:
 with tempfile.TemporaryDirectory(prefix='xos_p2d_') as d:
  d=Path(d);disk=d/'work.img';create_fat32(disk,512);transfer(disk,'mkdir','/bin');transfer(disk,'mkdir','/web')
  for src,dest in [(ROOT/'../XylophoneOS-ssg-p2-pagination/build/ssg-p2-regression/session.elf','session'),(ROOT/'build/p2d-browser/consumer.elf','ssg-consumer'),(ROOT/'build/p2d-browser2/browser.elf','browser')]:transfer(disk,'import','/bin/'+dest+'.elf',src)
  page=d/'ssg.html';page.write_bytes(b'<html><head><title>SSG fixture</title><style>body { margin:0; padding:16px; background:#f4f7fc; color:#23344e; font-size:16px; } .hidden { display:none; } .spacer { height:700px; }</style></head><body><h1>Visible Alpha</h1><a href="start.html">Native link target</a><div class="hidden"><p>HIDDEN_SECRET_FIXTURE</p></div><div class="spacer"></div><p>Below viewport omega</p><a href="garden.html">Bottom link</a></body></html>');transfer(disk,'import','/web/ssg.html',page)
  img=(ROOT/'../XylophoneOS-aurora-glass/build/aurora_glass/system-v5/xos.img').resolve();g=Guest(img,'p2d-guest/qemu',work_disk=disk);report['qemu_command']=g.command
  g.expect(b'xos64> ',timeout=45);send_bytes(g,b'run\r');g.expect_supervisor(trace=True,timeout=45);command(g,'demo quiet',b'demo tasks stopped');report['baseline']=resources(g);command(g,'display-start',b'result=0');g.expect(b'[display-service] ready');report['display']=resources(g)
  b=len(g.output);send_bytes(g,b'exec-driver /bin/session.elf /web/ssg.html browser-pages --browser --text\r');g.expect(b'SSG_PAGED_CONSUMER_DONE',start=b,timeout=150);g.expect(b'SSG_SESSION consumer_wait=',start=b,timeout=60)
  output=bytes(g.output)[b:];report['consumer_done']=[x.decode() for x in output.splitlines() if b'SSG_PAGED_CONSUMER_DONE' in x];print(report['consumer_done'],flush=True)
  report['status']='OBSERVED';g.qmp('input-send-event',{'events':[{'type':'key','data':{'down':True,'key':{'type':'qcode','data':'esc'}}},{'type':'key','data':{'down':False,'key':{'type':'qcode','data':'esc'}}}]});g.expect_supervisor(start=b,timeout=60);report['after']=resources(g)
except Exception as e:report['error']=repr(e);traceback.print_exc()
finally:
 if g:
  (out/'serial.log').write_bytes(g.output);g.close()
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
