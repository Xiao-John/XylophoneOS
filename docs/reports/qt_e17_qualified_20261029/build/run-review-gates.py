import subprocess,sys,json,hashlib
from pathlib import Path
r=Path.cwd();b=r/'build/qt_e17';out=b/'review_gates';out.mkdir(exist_ok=False);image=b/'review_system/xos.img'
report={'status':'FAILED','image_sha256':hashlib.sha256(image.read_bytes()).hexdigest(),'gates':{}}
cases=[('g05_interactive','qt6_widgets_acceptance.py','review_editor/notes.elf',['--case','interactive']),('g05_lifecycle','qt6_widgets_acceptance.py','review_editor/notes.elf',['--case','lifecycle']),('g05_no_vga','qt6_widgets_acceptance.py','review_editor/notes.elf',['--case','no-vga']),('aurora','qt6_aurora_acceptance.py','final_showcase/aurora_showcase.elf',[]),('widget_probe','qt6_widgets_probe.py','final_probe/widgets_probe.elf',[]),('save','qt6_save_acceptance.py','final_save/save_failures.elf',[]),('editor_errors','qt6_editor_errors.py','review_editor/notes.elf',[]),('resources','qt6_widgets_resources.py','final_resources/widgets_resources.elf',[])]
cases += [('g04_'+c,'qt6_gui_acceptance.py','final_gui/qt_demo.elf',['--case',c]) for c in ('pixels','interactive','lifecycle','no-vga')]
for name,runner,payload,extra in cases:
 cmd=[sys.executable,r/'tests'/runner,'--image',image,'--payload',b/payload,'--output',out/name,*extra]
 with (out/(name+'.runner.log')).open('wb') as log:code=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT).returncode
 file=out/name/'report.json';data=json.loads(file.read_text()) if file.exists() else {}
 report['gates'][name]={'status':'PASSED' if code==0 and data.get('status')=='PASSED' else 'FAILED','checks':len(data.get('checks',[])),'error':data.get('error'),'command':list(map(str,cmd))}
 print(name,report['gates'][name]['status'],flush=True);(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
report['status']='PASSED' if all(v['status']=='PASSED' for v in report['gates'].values()) else 'FAILED';(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
