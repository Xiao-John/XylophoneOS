# SPDX-License-Identifier: Apache-2.0
"""ISO capacity: real >4 MiB linked kernel, >1 MiB dash, bounds and reservation."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
import boot_smoke
from boot_smoke import Guest
from make_work_disk import create_fat32
from task_smoke import send_bytes
from xypm_image import Disk
from xypm_format import sha_file


def records(image):
    root=struct.unpack_from('<I',image,16*2048+158)[0]*2048
    result={};pos=root
    while image[pos]:
        n=image[pos];size=image[pos+32]
        result[bytes(image[pos+33:pos+33+size]).decode('ascii')]=pos
        pos+=n
        if pos>=root+2048:break
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir',type=Path,default=ROOT/'build/iso_capacity')
    parser.add_argument('--dash-manifest',type=Path,default=ROOT/'.cache/xos_seed/dash/8098a3cc28ff4ce74f5b/manifest.json')
    args=parser.parse_args();build=args.build_dir.resolve();output=build/'acceptance';output.mkdir(exist_ok=True)
    metadata=json.loads((build/'manifest.json').read_text())
    assert metadata['capacity_probe'] and not metadata['legacy_images_available']
    assert metadata['artifacts']['kernel.bin']['bytes']>4*1024*1024
    assert sha_file(build/'kernel.bin')==metadata['artifacts']['kernel.bin']['sha256']
    original=json.loads(args.dash_manifest.read_text());dash=Path(original['elf'])
    if not dash.is_absolute():dash=ROOT/dash
    assert sha_file(dash)==original['sha256']
    # Valid ELF trailer is intentionally outside LOADs; full on-disk bytes must survive.
    payload=output/'large_dash.elf';body=dash.read_bytes()
    count=(2<<20)+333-len(body);assert count>0
    trailer=(bytes(range(256))*((count+255)//256))[:count]
    payload.write_bytes(body+trailer)
    dash_manifest=output/'dash_manifest.json'
    dash_manifest.write_text(json.dumps({'elf':str(payload),'sha256':sha_file(payload)}))
    iso=output/'large.iso'
    subprocess.run([sys.executable,str(ROOT/'scripts/build_install_iso.py'),'--build-dir',str(build),
                    '--dash-manifest',str(dash_manifest),'--output',str(iso),
                    '--manifest',str(output/'install_manifest.json')],check=True)
    checks=[];report={'status':'failed','build_id':metadata['build_id'],'checks':checks,
                     'kernel_bytes':(build/'kernel.bin').stat().st_size,'kernel_sha256':sha_file(build/'kernel.bin'),
                     'payload_bytes':payload.stat().st_size,'payload_sha256':sha_file(payload),'iso_sha256':sha_file(iso),
                     'not_run':['real_hardware','arbitrary_power_loss','UEFI','stress']}
    guest=None
    def mark(name,**fields):checks.append({'name':name,'passed':True,**fields})
    try:
        disk=output/'fresh.img';assert not disk.exists(),'use a new acceptance output directory/image'
        create_fat32(disk,512)
        guest=Guest(iso,'iso_capacity/large',iso=True,work_disk=disk)
        guest.expect(b'xos64> ',timeout=45)
        guest.expect(b'capacity_probe_verified bytes=5242880')
        guest.expect(f'payload_bytes={payload.stat().st_size}'.encode())
        mark('real_linked_kernel_crosses_4_mib_and_full_probe_verified')
        # Verify actual readonly+NX mapping of the final probe page beyond 4 MiB.
        symbols={}
        for line in subprocess.check_output(['x86_64-elf-nm','-n',str(build/'kernel.elf')],text=True).splitlines():
            parts=line.split()
            if len(parts)==3:symbols[parts[2]]=int(parts[0],16)
        probe_end=symbols['capacity_probe_end']
        address=probe_end-4096
        pte_address=0x10000+(address//4096)*8
        guest.qmp('stop')
        pte_file=output/'probe_pte.bin'
        guest.qmp('human-monitor-command',{'command-line':f'pmemsave {pte_address:#x} 8 "{pte_file}"'})
        pte=struct.unpack('<Q',pte_file.read_bytes())[0]
        assert pte&1 and not pte&2 and pte&(1<<63),'large rodata mapping lost W^X'
        payload_file=output/'payload_ram.bin'
        guest.qmp('human-monitor-command',{'command-line':f'pmemsave 0x2000000 {payload.stat().st_size} "{payload_file}"'})
        assert sha_file(payload_file)==sha_file(payload),'loaded payload bytes differ'
        bitmap_symbol=next(value for name,value in symbols.items() if name.endswith('used_bitmapE'))
        bitmap_file=output/'used_bitmap.bin'
        guest.qmp('human-monitor-command',{'command-line':f'pmemsave {bitmap_symbol:#x} 16384 "{bitmap_file}"'})
        bitmap=bitmap_file.read_bytes()
        for page in range(0x2000000//4096,(0x2000000+payload.stat().st_size+4095)//4096):
            assert bitmap[page//8]&(1<<(page%8)),'payload page was left allocatable'
        guest.qmp('cont')
        mark('large_rodata_readonly_nx_and_payload_ram_full_hash',pte=hex(pte))
        mark('every_payload_page_reserved_from_allocator')
        start=len(guest.output);send_bytes(guest,b'run\r')
        guest.expect_supervisor(start=start,timeout=60)
        guest.expect(b'[files] dash installed bytes=',start=start,timeout=60)
        start=len(guest.output);send_bytes(guest,b'dash -i\r')
        guest.expect(b'$ ',start=start,timeout=45)
        start=len(guest.output);send_bytes(guest,b'echo ISO_CAPACITY_OK\r')
        guest.expect(b'ISO_CAPACITY_OK',start=start,timeout=45)
        guest.expect(b'$ ',start=start,timeout=45)
        start=len(guest.output);send_bytes(guest,b'exit\r')
        guest.expect_supervisor(start=start,timeout=45)
        # A later allocator-backed ELF launch and file writes must not reuse payload pages.
        start=len(guest.output);send_bytes(guest,b'sync\r')
        guest.expect(b'[files] sync=ok',start=start,timeout=30);guest.expect_supervisor(start=start)
        guest.close();guest=None
        with Disk(disk,output,True) as volume:
            installed=volume.export('/usr/bin/dash')
            assert sha_file(installed)==sha_file(payload),'installed payload differs, including trailer'
        mark('large_payload_streamed_to_fat_and_dash_runs_full_hash_matches')
        # Source payload survives allocations throughout running user tasks.
        serial=(ROOT/'build/iso_capacity/large_serial.log').read_bytes()
        assert b'BOOT_ERROR' not in serial and b'[panic]' not in serial
        base=bytearray(iso.read_bytes());entries=records(base)
        failures=[('kernel_size','KERNEL.BIN;1',10,9<<20,b'BOOT_ERROR: iso_kernel_size'),
                  ('payload_size','DASH.ELF;1',10,33<<20,b'BOOT_ERROR: iso_payload_size'),
                  ('extent','DASH.ELF;1',2,len(base)//2048+1,b'BOOT_ERROR: iso_extent')]
        for name,entry,field,value,message in failures:
            malformed=bytearray(base);offset=entries[entry]+field
            struct.pack_into('<I',malformed,offset,value);struct.pack_into('>I',malformed,offset+4,value)
            path=output/(name+'.iso');path.write_bytes(malformed)
            guest=Guest(path,'iso_capacity/'+name,iso=True)
            guest.expect(message,timeout=25)
            assert b'event=kernel_enter' not in guest.output
            guest.close();guest=None;mark('reject_'+name)
        malformed=bytearray(base);malformed[entries['KERNEL.BIN;1']]=3
        path=output/'directory.iso';path.write_bytes(malformed)
        guest=Guest(path,'iso_capacity/directory',iso=True);guest.expect(b'BOOT_ERROR: iso_directory',timeout=25)
        guest.close();guest=None;mark('reject_truncated_directory_record')
        command=boot_smoke.qemu_command
        def small_ram(*a,**kw):
            result=command(*a,**kw);result[result.index('-m')+1]='32M';return result
        with mock.patch('boot_smoke.qemu_command',small_ram):guest=Guest(iso,'iso_capacity/ram',iso=True)
        guest.expect(b'BOOT_ERROR: iso_payload_memory',timeout=25)
        guest.close();guest=None;mark('reject_payload_outside_actual_usable_ram')
        # Corrupt an actual linked section byte, rather than relying on loader progress text.
        malformed=bytearray(base);record=entries['KERNEL.BIN;1']
        extent=struct.unpack_from('<I',malformed,record+2)[0]
        malformed[extent*2048+symbols['capacity_probe_begin']-0x100000+5242879]^=1
        path=output/'corrupt_probe.iso';path.write_bytes(malformed)
        guest=Guest(path,'iso_capacity/corrupt_probe',iso=True)
        guest.expect(b'reason=capacity_probe_corrupt',timeout=25)
        guest.close();guest=None;mark('reject_corrupt_linked_probe_tail')
        report['status']='passed'
    finally:
        if guest:guest.close()
        (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
