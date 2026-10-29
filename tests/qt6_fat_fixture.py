# SPDX-License-Identifier: Apache-2.0
"""Mutate only disposable FAT fixtures for G05 read-only/full tests."""
import struct
def alter(disk,mode):
 with disk.open('r+b') as f:
  boot=f.read(512);bps=struct.unpack_from('<H',boot,11)[0];spc=boot[13];reserved=struct.unpack_from('<H',boot,14)[0];fats=boot[16];fatsz=struct.unpack_from('<I',boot,36)[0];total=struct.unpack_from('<I',boot,32)[0];root=struct.unpack_from('<I',boot,44)[0];data=reserved+fats*fatsz
  if mode=='readonly':
   pos=(data+(root-2)*spc)*bps;f.seek(pos);block=f.read(spc*bps)
   for i in range(0,len(block),32):
    if block[i:i+11]==b'LOCK    TXT':f.seek(pos+i+11);f.write(bytes([block[i+11]|1]));return
   raise AssertionError('LOCK.TXT not found')
  for fat in range(fats):
   f.seek((reserved+fat*fatsz)*bps);table=bytearray(f.read(fatsz*bps))
   for c in range(2,(total-data)//spc+2):
    if struct.unpack_from('<I',table,c*4)[0]&0xfffffff==0:struct.pack_into('<I',table,c*4,0xfffffff)
   f.seek((reserved+fat*fatsz)*bps);f.write(table)
  for sector in (1,7):f.seek(sector*bps+488);f.write(struct.pack('<I',0))
