# SPDX-License-Identifier: Apache-2.0
"""G02: real BIOS/QEMU pixels, PS/2 events, permissions and lifecycle recovery."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import tempfile
import time
from unittest.mock import patch

ROOT=Path('/Users/perry_guo/Documents/ChatGPT/os/XylophoneOS-net-clock-irq-repair/build/clock_irq/runs/display_smoke')
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
import boot_smoke
from boot_smoke import Guest
from make_work_disk import create_fat32
from task_smoke import send_bytes,pump
from process_smoke import resources


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'build/display_acceptance')
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    log_prefix=str(out.relative_to(ROOT/'build'))
    build=ROOT/'build';manifest=json.loads((build/'manifest.json').read_text())
    report={'status':'failed','build_id':manifest['build_id'],'checks':[],
            'source_sha256':manifest['source_digest'] if 'source_digest' in manifest else manifest.get('source_sha256'),
            'image_sha256':sha(build/'xos-install.iso'),'not_run':['real_hardware','SMP','Qt','long_term_stress']}
    guest=None
    def mark(name,**fields):report['checks'].append({'name':name,'status':'passed',**fields})
    def command(line,expected=b'xsh> ',timeout=30):
        start=len(guest.output);send_bytes(guest,line.encode()+b'\r')
        guest.expect(expected,start=start,timeout=timeout)
        guest.expect_supervisor(start=start,timeout=timeout)
        return bytes(guest.output)[start:]
    def trace_pid(output):
        match=re.search(rb'\[display-start\] pid=(\d+) result=0',output);assert match,output
        return int(match[1])
    def service_start():
        start=len(guest.output);output=command('display-start',b'result=0')
        guest.expect(b'[display-service] ready file=denied block=denied spawn=denied',start=start)
        return trace_pid(output)
    def event_send(events):guest.qmp('input-send-event',{'events':events})
    def key(name,down):event_send([{'type':'key','data':{'down':down,'key':{'type':'qcode','data':name}}}])
    def rel(axis,value):return {'type':'rel','data':{'axis':axis,'value':value}}
    def button(name,down):return {'type':'btn','data':{'down':down,'button':name}}
    def events_since(start):
        pattern=rb'\[gfx-event\] seq=(\d+) ns=(\d+) kind=(\d+) code=(\d+) mods=(\d+) buttons=(\d+) dx=(-?\d+) dy=(-?\d+) x=(\d+) y=(\d+) lost=(\d+)'
        return [tuple(map(int,m)) for m in re.findall(pattern,bytes(guest.output)[start:])]
    def boot(image,name,disk,iso=False,no_vga=False):
        original=boot_smoke.qemu_command
        def qemu(*a,**kw):
            command=original(*a,**kw)
            if no_vga:command[command.index('-vga')+1]='none'
            return command
        with patch.object(boot_smoke,'qemu_command',qemu):g=Guest(image,name,work_disk=disk,iso=iso)
        g.expect(b'xos64> ',timeout=40)
        return g
    try:
        # Recheck every frozen input/output, not only a screenshot or success marker.
        for name,digest in manifest['sources'].items():assert sha(ROOT/name)==digest,name
        for name,info in manifest['artifacts'].items():assert sha(build/name)==info['sha256'],name
        mark('source_and_artifact_hashes_match_manifest')
        with tempfile.TemporaryDirectory(prefix='xos_e14_') as directory:
            disk=Path(directory)/'work.img';create_fat32(disk,512)
            guest=boot(build/'xos-install.iso',log_prefix+'/main',disk)
            assert b'width=800 height=600 stride=3200' in guest.output
            physical=int(re.search(rb'\[display\][^\r\n]*physical=(0x[0-9a-f]+)',guest.output)[1],16)
            send_bytes(guest,b'run\r');guest.expect_supervisor(trace=True);pump(guest,1.6)
            guest.expect(b'[input] ps2=ready irq1=enabled irq12=enabled')
            baseline=resources(guest);report['resource_baseline']=baseline
            service=service_start();with_service=resources(guest)
            mark('service_role_denies_file_block_and_spawn',pid=service,resources=with_service)
            output=command('exec gfxdemo deny',b'kind=exited code=0')
            assert output.count(b'=pass')==4;assert resources(guest)==with_service
            mark('ordinary_process_cannot_grant_present_read_input_or_focus')
            command('exec gfxdemo threads',b'[gfx] threads=pass');assert resources(guest)==with_service
            mark('two_real_threads_share_pid_and_cannot_escalate_display_authority')
            command('exec gfxdemo mmio',b'kind=faulted');assert resources(guest)==with_service
            mark('ring3_mmio_aperture_access_faults_and_revokes_surface')
            output=command('exec gfxdemo check',b'[gfx] checks=pass')
            assert len(re.findall(rb'\[gfx-check\] [^\n]*=pass',output))==23;assert b'kind=exited code=0' in output
            assert resources(guest)==with_service
            mark('guest_display_mode_bounds_format_pointer_quota_focus_checks',count=23)
            # Device bytes and QEMU scanout independently agree with software drawing.
            framebuffer=out/'framebuffer.bin'
            guest.qmp('pmemsave',{'val':physical,'size':1920000,'filename':str(framebuffer)})
            expected=bytearray(struct.pack('<I',0x102030)*800*600)
            def rect(x,y,w,h,color):
                row=struct.pack('<I',color)*w
                for yy in range(y,y+h):expected[(yy*800+x)*4:(yy*800+x+w)*4]=row
            for i,c in enumerate([0xe74c3c,0xf39c12,0xf1c40f,0x2ecc71,0x1abc9c,0x3498db,0x9b59b6,0xec70a6]):
                rect(40+i*70,120,56,240-i*12,c)
            rect(4,4,12,12,0xabcdef)
            assert framebuffer.read_bytes()==expected,'device pixel mismatch or rejected write changed framebuffer'
            ppm=out/'xylophone.ppm';guest.qmp('screendump',{'filename':str(ppm)})
            from PIL import Image
            image=Image.open(ppm);assert image.size==(800,600)
            assert image.getpixel((5,5))==(0xab,0xcd,0xef)
            assert image.getpixel((40,120))==(0xe7,0x4c,0x3c)
            image.save(out/'xylophone.png')
            mark('full_and_dirty_present_match_all_1920000_device_bytes_and_scanout',physical=physical,
                 framebuffer_sha256=sha(framebuffer),screenshot_sha256=sha(out/'xylophone.png'))
            # Real device input via QMP, never a call into a guest handler.
            start=len(guest.output);send_bytes(guest,b'exec gfxdemo hold\r');guest.expect(b'[gfx] ready',start=start)
            key('shift',True);key('a',True);key('a',False);key('shift',False);pump(guest,0.4)
            event_send([rel('x',31),rel('y',-17)]);pump(guest,0.3)
            event_send([button('left',True)]);pump(guest,0.3)
            event_send([button('left',False)]);pump(guest,0.3)
            ev=events_since(start);report['input_events']=ev
            keyboard=[e for e in ev if e[2] in (1,2)]
            assert [(e[2],e[3]) for e in keyboard[:4]]==[(1,42),(1,30),(2,30),(2,42)],ev
            assert keyboard[1][4]&1 and not keyboard[3][4]&1
            mice=[e for e in ev if e[2]==3]
            assert any(e[6]==31 and e[7]==-17 and e[8:10]==(431,283) for e in mice),ev
            assert any(e[5]&1 for e in mice) and mice[-1][5]==0,ev
            assert all(a[0]<b[0] and a[1]<=b[1] for a,b in zip(ev,ev[1:])),ev
            # Busy second client cannot take over focus or access another channel.
            key('q',True);key('q',False);guest.expect(b'[gfx] closed',start=start);guest.expect_supervisor(start=start)
            assert resources(guest)==with_service
            mark('qmp_ps2_keyboard_order_modifiers_mouse_motion_click_release_and_monotonic_time')
            # Queue exhaustion while the guest deliberately does not consume it.
            start=len(guest.output);send_bytes(guest,b'exec gfxdemo overflow\r');guest.expect(b'[gfx] ready',start=start)
            for _ in range(80):key('b',True);key('b',False);time.sleep(0.002)
            guest.expect(b'[gfx] overflow_drain',start=start,timeout=15);pump(guest,0.8)
            ev=events_since(start);assert any(e[2]==4 and e[10]>=65 for e in ev),ev
            assert all(a[0]<b[0] for a,b in zip(ev,ev[1:])),ev
            key('q',True);key('q',False);guest.expect(b'[gfx] closed',start=start);guest.expect_supervisor(start=start)
            assert resources(guest)==with_service
            mark('real_ps2_queue_overflow_reports_loss_and_resynchronization',events=ev)
            # No focus: hardware input is discarded and acquisition clears state.
            key('ctrl',True);key('c',True);pump(guest,0.1);key('c',False);key('ctrl',False)
            output=command('exec gfxdemo check',b'checks=pass');assert resources(guest)==with_service
            mark('no_focus_events_discarded_and_next_surface_state_clean')
            for iteration in range(4):
                output=command('exec gfxdemo fault',b'kind=faulted')
                assert b'fault_after_connect' in output and b'vector=6' in output
                assert resources(guest)==with_service
                command('exec gfxdemo check',b'checks=pass');assert resources(guest)==with_service
            mark('four_faulted_clients_reclaimed_and_next_client_recovers')
            # Service death wakes a blocked live client, revokes handles and focus.
            start=len(guest.output);send_bytes(guest,b'spawn gfxdemo hold\r');guest.expect(b'[gfx] ready',start=start)
            output=command(f'kill {service}',b'xsh> ')
            guest.expect(b'[gfx] closed',start=start)
            pump(guest,0.2)
            # Collect both parent's completion records before exact comparison.
            created=re.findall(rb'\[loader\] started pid=(\d+) image=gfxdemo',bytes(guest.output)[start:])
            assert created,bytes(guest.output)[start:]
            command(f'wait {int(created[0])}',b'kind=exited')
            command(f'wait {service}',b'kind=killed')
            assert resources(guest)==baseline,(baseline,resources(guest))
            mark('service_killed_while_client_waits_wakes_client_and_releases_all_resources')
            for _ in range(3):
                service=service_start();command('exec gfxdemo check',b'checks=pass')
                command('exec gfxdemo stop',b'kind=exited code=0')
                command(f'wait {service}',b'kind=exited code=0')
                assert resources(guest)==baseline
            mark('three_service_start_stop_cycles_return_exact_resource_baseline')
            # Real partial physical OOM, with two resident 200MiB applications.
            hogs=[]
            for _ in range(2):
                start=len(guest.output);send_bytes(guest,b'spawn gfxdemo memhold\r')
                guest.expect(b'[gfx] memory_held',start=start,timeout=60)
                output=bytes(guest.output)[start:]
                hogs.append(int(re.search(rb'\[loader\] started pid=(\d+)',output)[1]))
            command('exec gfxdemo oom',b'physical_oom_rollback=pass',timeout=90)
            for hog in hogs:
                command(f'kill {hog}');command(f'wait {hog}',b'kind=killed')
            assert resources(guest)==baseline
            mark('real_physical_memory_exhaustion_rolls_back_partial_allocation_and_all_resources')
            start=len(guest.output);output=command('display-start fault',b'result=0');service=trace_pid(output)
            command('exec gfxdemo check',b'kind=exited code=2')
            guest.expect(b'[display-service] fault_after_request',start=start)
            command(f'wait {service}',b'kind=faulted')
            assert resources(guest)==baseline
            service=service_start();command('exec gfxdemo check',b'checks=pass')
            command('exec gfxdemo stop',b'kind=exited code=0');command(f'wait {service}',b'kind=exited code=0')
            assert resources(guest)==baseline
            mark('real_service_exception_releases_pending_request_and_restart_recovers')
            # Existing rescue, user loader, libc and persistent files still operate.
            command('exec demo e14',b'kind=exited code=42')
            command('exec libc_hello',b'kind=exited code=7')
            command('filetest',b'xsh> ');command('sync',b'[files] sync=ok')
            assert resources(guest)==baseline
            mark('serial_xshell_loader_libc_file_service_and_sync_remain_usable')
            guest.close();guest=None
            # Both ISO loaders carry the extension; file-backed boot is the default route.
            for image in ('xos.iso','xos-install.iso'):
                guest=boot(build/image,log_prefix+'/'+image,disk,iso=True)
                assert b'width=800 height=600 stride=3200' in guest.output
                send_bytes(guest,b'run\r');guest.expect_supervisor(trace=True);pump(guest,1.5)
                service=service_start();command('exec gfxdemo check',b'checks=pass')
                mark('bios_'+image+'_graphics_and_guest_checks')
                guest.close();guest=None
            guest=boot(build/'xos-install.iso',log_prefix+'/no_vga',disk,iso=True,no_vga=True)
            assert b'[display] state=ready' not in guest.output
            send_bytes(guest,b'run\r');guest.expect_supervisor(trace=True);pump(guest,1.5)
            output=command('display-start',b'result=-19');assert b'result=-19' in output
            command('exec demo rescue',b'kind=exited code=42')
            command('stats',b'completions=')
            mark('no_graphics_device_boots_and_serial_rescue_operates')
            guest.close();guest=None
        report['status']='passed'
    except Exception as error:
        report['error']=repr(error);raise
    finally:
        if guest is not None:guest.close()
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f"G02 {report['status']}: {len(report['checks'])} groups | {report['build_id']}")

if __name__=='__main__':main()
