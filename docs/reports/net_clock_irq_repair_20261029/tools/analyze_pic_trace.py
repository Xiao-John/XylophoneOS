import collections,hashlib,json,re,sys
from pathlib import Path
p=Path(sys.argv[1]);lines=p.read_text().splitlines();counts=collections.Counter();expected=None;acks=[];errors=[];complete=0;first=None
for i,line in enumerate(lines):
 m=re.fullmatch(r'pic_interrupt irq (\d+) intno (\d+)',line)
 if m:
  irq,vector=map(int,m.groups())
  if not 32<=vector<=47:continue
  if first is None:first=i
  if expected is not None:
   if acks!=expected:errors.append({'line':i,'acks':acks,'expected':expected})
   else:complete+=1
  counts[str(irq)]+=1;expected=([0,1] if irq>=8 else [1]);acks=[]
 elif first is not None:
  m=re.fullmatch(r'pic_ioport_write master (\d+) addr 0x0 val 0x20',line)
  if m:acks.append(int(m[1]))
if expected is not None:
 if acks==expected:complete+=1
 else:errors.append({'tail':True,'acks':acks,'expected':expected})
r={'status':'PASSED' if not errors and counts.get('0') and counts.get('10') else 'FAILED','scope':'actual QEMU delivered OS IRQs and matching slave/master EOI writes; no kernel EOI statistics','trace_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'OS_IRQ_counts':dict(counts),'complete_irq_eoi_sequences':complete,'errors':errors,'firmware_events_excluded':first}
p.with_name('analysis.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2));raise SystemExit(r['status']!='PASSED')
