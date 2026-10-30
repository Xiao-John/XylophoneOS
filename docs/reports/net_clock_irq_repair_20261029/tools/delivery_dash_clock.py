import hashlib,json,os,re,shutil,sys,time
from pathlib import Path
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'tests')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from work_disk import transfer
from task_smoke import send_bytes
from process_smoke import command,resources
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
O=R/'build/clock_irq/delivery_dash_clock';O.mkdir();D=O/'work.img';create_fat32(D,512)
for n in ['/bin','/work']:transfer(D,'mkdir',n)
clock=R/'build/clock_irq/inputs/delivery_clock_libc.elf';dash=R.parent/'XylophoneOS-dash-c1-c3/build/dash_c3_frozen/dash.elf'
transfer(D,'import','/bin/clock',clock);transfer(D,'import','/bin/dash',dash);script=O/'clock.sh';script.write_text('(exec /bin/clock); echo CLOCK_DASH:$?\n');transfer(D,'import','/work/clock.sh',script)
I=R/'build/clock_irq/delivery_default/xos.img';r={'status':'FAILED','image_sha256':sha(I),'clock_elf_sha256':sha(clock),'dash_elf_sha256':sha(dash),'script_sha256':sha(script),'disk_before_sha256':sha(D)};g=None
try:
 g=Guest(I,'clock_irq/delivery_dash_clock',work_disk=D);r['existing_authority']='explicit supervisor spawn/exec delegation via exec-driver; no hardware/device grant';r['qemu_command']=g.command;g.expect(b'xos64> ',timeout=40)
 for name in ['net-test','irq-audit']:
  start=len(g.output);send_bytes(g,(name+'\r').encode());g.expect(b'ERROR: unknown_command',start=start);g.expect(b'xos64> ',start=start)
 r['default_image_test_commands_absent']='PASSED'
 start=len(g.output);send_bytes(g,b'run\r');g.expect_supervisor(trace=True,start=start,timeout=40);command(g,'demo quiet',b'demo tasks');base=resources(g);r['resources_before']=base
 result=command(g,'exec-driver /bin/dash /work/clock.sh',b'kind=exited code=0',timeout=40);assert b'CLOCK_DASH:0' in result and b'CLOCK_USER_OK:' in result,result;assert resources(g)==base;r['resources_after']=resources(g);r['status']='PASSED'
except Exception as e:r['error']=repr(e)
finally:
 if g:
  g.close()
  for k in ['serial','qemu']:shutil.copyfile(R/f'build/{g.name}_{k}.log',O/(k+'.log'))
 r['disk_after_sha256']=sha(D);(O/'report.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps(r,indent=2));raise SystemExit(r['status']!='PASSED')
