#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Validate a frozen FB0 report and resolve its instruction with bound ELF files."""
import argparse, hashlib, json, os, re, stat, subprocess, tempfile
from pathlib import Path

class Invalid(ValueError): pass

def require(ok, message):
    if not ok: raise Invalid(message)

def pairs(items):
    result = {}
    for k, v in items:
        require(k not in result, 'duplicate JSON key')
        result[k] = v
    return result

def obj(value, keys):
    require(type(value) is dict and set(value) == set(keys), 'unexpected fields')
    return value

def number(value, lo, hi):
    require(type(value) is int and lo <= value <= hi, 'invalid integer')

def hexstr(value, n):
    require(type(value) is str and re.fullmatch('[0-9a-f]{%d}' % n, value), 'invalid hex')

def decimal(value, lo, hi):
    require(type(value) is str and re.fullmatch(r'0|-?[1-9][0-9]*', value), 'invalid decimal')
    require(lo <= int(value) <= hi, 'decimal overflow')

def string(value, limit, nullable=True):
    if nullable and value is None: return
    require(type(value) is str and 0 < len(value.encode('utf-8')) <= limit, 'invalid string')

def read_bounded(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_size <= limit, 'invalid file')
        with os.fdopen(fd, 'rb', closefd=False) as f: data = f.read(limit + 1)
        after = os.fstat(fd)
        require(len(data) <= limit and len(data) == info.st_size and
                (info.st_size,info.st_mtime_ns,info.st_ctime_ns)==(after.st_size,after.st_mtime_ns,after.st_ctime_ns),
                'oversized or changed file')
        return data
    finally: os.close(fd)

def load(data):
    require(not data.startswith(b'\xef\xbb\xbf'), 'BOM rejected')
    def reject(_): raise Invalid('nonfinite JSON')
    value = json.loads(data.decode('utf-8'), object_pairs_hook=pairs, parse_constant=reject)
    def walk(v, depth):
        require(depth <= 8, 'JSON nesting limit')
        if type(v) is dict:
            for x in v.values(): walk(x, depth + 1)
        elif type(v) is list:
            for x in v: walk(x, depth + 1)
    walk(value, 1)
    return value

def validate(directory):
    require(directory.is_dir() and not directory.is_symlink(), 'invalid report directory')
    expected = {'report.json', 'image.json', 'context.json', 'manifest.json'}
    entries = list(directory.iterdir())
    require(len(entries) == 4 and {p.name for p in entries} == expected, 'unexpected report files')
    raw = {p.name: read_bounded(p, 8192) for p in entries}
    require(sum(map(len, raw.values())) <= 32768, 'report too large')
    report, image, context, manifest = (load(raw[n]) for n in ('report.json','image.json','context.json','manifest.json'))
    obj(report, ('version','run_id','status_version','outcome','pid','code','vector','address','instruction'))
    obj(image, ('version','run_id','source','size','sha256','elf_type','sdk_profile','build_id'))
    obj(context, ('version','run_id','collector_version','system_build_id','monotonic_ns','utc_ns'))
    obj(manifest, ('version','run_id','state','files'))
    for d in (report,image,context,manifest):
        require(type(d['version']) is int and d['version'] == 1, 'version mismatch')
        hexstr(d['run_id'],32); require(d['run_id'] == report['run_id'], 'run ID mismatch')
    require(type(report['status_version']) is int and report['status_version'] == 1, 'status version')
    require(report['outcome'] in ('exited','faulted','killed'), 'outcome')
    hexstr(report['pid'],16);decimal(report['code'],-(1<<63),(1<<63)-1)
    if report['outcome'] == 'faulted':
        number(report['vector'],0,255);hexstr(report['instruction'],16)
        if report['vector'] == 14: hexstr(report['address'],16)
        else: require(report['address'] is None,'unexpected address')
    else: require(all(report[k] is None for k in ('vector','address','instruction')), 'unexpected fault data')
    require(image['source'] in ('file','unknown'), 'image source')
    if image['source'] == 'file': number(image['size'],0,0xffffffff);hexstr(image['sha256'],64)
    else: require(image['size'] is None and image['sha256'] is None, 'unknown image identity')
    require(image['elf_type'] in ('ET_EXEC',None),'ELF type')
    string(image['sdk_profile'],128);string(image['build_id'],128)
    string(context['collector_version'],64,False);string(context['system_build_id'],128)
    if context['monotonic_ns'] is not None: decimal(context['monotonic_ns'],0,(1<<64)-1)
    if context['utc_ns'] is not None: decimal(context['utc_ns'],-(1<<63),(1<<63)-1)
    require(manifest['state']=='complete', 'incomplete manifest')
    files = obj(manifest['files'], ('report.json','image.json','context.json'))
    for name, record in files.items():
        obj(record, ('size','sha256'));number(record['size'],0,8192);hexstr(record['sha256'],64)
        require(record['size']==len(raw[name]) and record['sha256']==hashlib.sha256(raw[name]).hexdigest(),'file digest mismatch')
    return report, image

def symbolize(directory, running, symbols, receipt, addr2line, objcopy="x86_64-elf-objcopy"):
    report, image = validate(directory)
    require(report['outcome']=='faulted' and image['source']=='file' and image['elf_type']=='ET_EXEC', 'no resolvable fault image')
    runbytes = read_bounded(running, 64*1024*1024)
    symbytes = read_bounded(symbols, 64*1024*1024)
    binding = obj(load(read_bounded(receipt,8192)), ('version','running_sha256','symbols_sha256'))
    require(type(binding['version']) is int and binding['version']==1, 'binding version')
    hexstr(binding['running_sha256'],64);hexstr(binding['symbols_sha256'],64)
    require(len(runbytes)==image['size'] and hashlib.sha256(runbytes).hexdigest()==image['sha256']==binding['running_sha256'], 'running ELF mismatch')
    require(hashlib.sha256(symbytes).hexdigest()==binding['symbols_sha256'], 'symbol ELF mismatch')
    import struct
    require(runbytes[:6]==b'\x7fELF\x02\x01' and len(runbytes)>=64, 'invalid ELF64')
    require(struct.unpack_from('<HH',runbytes,16)==(2,62), 'unsupported ELF')
    off=struct.unpack_from('<Q',runbytes,32)[0]; entsize,count=struct.unpack_from('<HH',runbytes,54)
    require(entsize>=56 and count<=1024 and off+entsize*count<=len(runbytes), 'bad ELF program headers')
    address=int(report['instruction'],16);inside=False
    for i in range(count):
        kind, flags, _, va, _, _, mem, _=struct.unpack_from('<IIQQQQQQ',runbytes,off+i*entsize)
        if kind==1 and flags&1 and va <= address < va+mem and va+mem <= 1<<64: inside=True
    require(inside,'instruction outside executable segment')
    with tempfile.TemporaryDirectory(prefix='xos_fb2_symbols_') as folder:
        snapshot=Path(folder)/'symbols.elf';snapshot.write_bytes(symbytes)
        stripped=Path(folder)/'stripped.elf'
        subprocess.run([objcopy,'--strip-debug',str(snapshot),str(stripped)],capture_output=True,timeout=30,check=True)
        require(stripped.read_bytes()==runbytes,'symbol ELF does not reproduce running ELF')
        result=subprocess.run([addr2line,'-f','-C','-e',str(snapshot),hex(address)],capture_output=True,text=True,timeout=15,check=True)
    lines=result.stdout.splitlines();require(len(lines)>=2 and lines[1] not in ('??:0','??:?'), 'symbol not resolved')
    return {'run_id':report['run_id'],'instruction':hex(address),'function':lines[0],'location':lines[1]}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('report',type=Path);p.add_argument('--running',type=Path,required=True);p.add_argument('--symbols',type=Path,required=True);p.add_argument('--binding',type=Path,required=True);p.add_argument('--addr2line',default='x86_64-elf-addr2line');p.add_argument('--objcopy',default='x86_64-elf-objcopy')
    args=p.parse_args()
    try: print(json.dumps(symbolize(args.report,args.running,args.symbols,args.binding,args.addr2line,args.objcopy),ensure_ascii=False))
    except (Invalid,OSError,UnicodeError,ValueError,RecursionError,subprocess.SubprocessError) as e: p.exit(1,'fb2: '+str(e)+'\n')
if __name__=='__main__': main()
