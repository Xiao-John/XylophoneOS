# SPDX-License-Identifier: Apache-2.0
"""P1 offline, copy-on-output package transactions. Never modifies the source image."""
import fcntl
import hashlib
import os
from pathlib import Path
import selectors
import shutil
import stat
import subprocess
import tempfile
import uuid

from xypm_format import (canonical, check_profile, confined, fields, load_json, path_name,
                         require, sha_file, validate_manifest, verify_package)

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = '/var/lib/xypm/db.json'
INDEX_PATH = '/var/lib/xypm/index.tsv'
MAX_PACKAGES = 64
MAX_OWNED_FILES = 8192


def host_tool():
    sources = [ROOT/'scripts/xypm_disk_host.cpp', ROOT/'src/third_party/fatfs/ff.c',
               ROOT/'src/user/services/fatfs_unicode.cpp']
    headers = sorted((ROOT/'src/third_party/fatfs').glob('*.h'))
    snapshots = {p.name: p.read_bytes() for p in sources + headers}
    digest = hashlib.sha256(canonical({n: hashlib.sha256(b).hexdigest() for n,b in snapshots.items()})).hexdigest()
    folder = ROOT/'.cache/xos_seed/xypm_host'/digest
    folder.mkdir(parents=True, exist_ok=True)
    output = folder/'xypm_disk_host'
    if not output.exists():
        for name, data in snapshots.items():
            (folder/name).write_bytes(data)
        compiler = shutil.which('clang++') or shutil.which('c++')
        require(compiler is not None, 'host C++ compiler required')
        subprocess.run([compiler,'-std=c++17','-O2','-w','-I',str(folder),
                        *[str(folder/p.name) for p in sources],'-o',str(output)],check=True)
    return output


class Disk:
    def __init__(self, image, folder, read_only=False):
        self.folder, self.serial = Path(folder), 0
        self.export_prefix = uuid.uuid4().hex
        self.process = subprocess.Popen([str(host_tool()),str(image)] + (['--read-only'] if read_only else []),
                                        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout,selectors.EVENT_READ)
        try:
            require(self._read() == ['OK'], 'cannot mount/lock image')
        except BaseException:
            self.close(force=True)
            raise

    def _read(self):
        require(bool(self.selector.select(30)), 'offline image backend timed out')
        data = self.process.stdout.readline(4096)
        require(bool(data) and data.endswith(b'\n'), 'offline image backend exited or bad response')
        return data[:-1].decode('utf-8','strict').split('\t')

    def command(self, *args):
        require(all(not any(c in str(arg) for c in '\t\n\r\x00') for arg in args), 'invalid backend argument')
        self.process.stdin.write(('\t'.join(map(str,args))+'\n').encode());self.process.stdin.flush()
        result = self._read()
        require(result[0] in ('OK','MISSING'), 'FatFs operation failed: '+str(args[0])+' '+str(result))
        return result

    def info(self, path):
        result = self.command('stat',path)
        if result == ['MISSING']:return None
        require(len(result) == 5 and result[1] in ('F','D'), 'invalid file metadata')
        require(result[3].lower() == Path(path).name.lower(), 'FAT alias/canonical-name conflict: '+path)
        return {'directory':result[1]=='D','size':int(result[2])}

    def check_parents(self, path):
        parts = path.strip('/').split('/')
        for i in range(1,len(parts)):
            found = self.info('/'+'/'.join(parts[:i]))
            require(found is None or found['directory'], 'parent is a file: '+path)

    def export(self, path):
        self.serial += 1
        dest = self.folder/('export_'+self.export_prefix+'_'+str(self.serial))
        self.command('export',path,dest)
        return dest

    def close(self, force=False):
        try:
            if self.process.poll() is None:
                if force:
                    self.process.kill()
                else:
                    self.command('quit')
            self.process.wait(timeout=10)
            if not force:require(self.process.returncode==0,'offline image session failed')
        finally:
            if self.process.poll() is None:self.process.kill();self.process.wait()
            self.selector.close()
            for stream in (self.process.stdin,self.process.stdout,self.process.stderr):stream.close()

    def __enter__(self):return self
    def __exit__(self, kind, value, trace):self.close(force=kind is not None)


def index_bytes(db):
    def escaped(value):
        return ''.join('\\'+c if c=='\\' else ('\\x%02x'%ord(c) if ord(c)<32 or ord(c)==127 else c) for c in value)
    lines=['xypm-index-v1']
    for name,record in sorted(db['packages'].items()):
        manifest=record['manifest']
        lines.append('\t'.join((name,escaped(manifest['upstream_version']),str(manifest['revision']),record['sha256'],manifest['target_profile'])))
    return ('\n'.join(lines)+'\n').encode('utf-8')


def owners(db):
    result={}
    for name,record in db['packages'].items():
        for item in record['manifest']['files']:
            folded=item['path'].lower()
            require(folded not in result,'database has duplicate file ownership')
            result[folded]=name
    require(len(result)<=MAX_OWNED_FILES,'installed file limit exceeded')
    return result


def load_db(disk, profile):
    # Refuse parallel ownership databases left by pre-rename development images.
    for old_name in ('xpm', 'xpkg'):
        for leaf in ('db.json', 'index.tsv'):
            require(disk.info('/var/lib/'+old_name+'/'+leaf) is None,
                    'legacy package database found; migrate a copy before using xypm')
    disk.check_parents(DB_PATH)
    info=disk.info(DB_PATH)
    if info is None:
        require(disk.info(INDEX_PATH) is None,'orphan xypm index without database')
        return {'format_version':1,'target_profile':profile['id'],'packages':{},'created_directories':[],
                'index_sha256':hashlib.sha256(b'xypm-index-v1\n').hexdigest()}
    require(not info['directory'] and info['size']<=1<<20,'invalid xypm database size/type')
    db=load_json(disk.export(DB_PATH))
    fields(db,('format_version','target_profile','packages','created_directories','index_sha256'))
    require(type(db['format_version']) is int and db['format_version']==1 and db['target_profile']==profile['id'],'database profile/version mismatch')
    require(type(db['packages']) is dict and len(db['packages'])<=MAX_PACKAGES,'invalid package database')
    require(type(db['created_directories']) is list and len(db['created_directories'])<=MAX_OWNED_FILES*4,'invalid directory ownership')
    for path in db['created_directories']:
        path_name(path,managed=False);require(path=='usr' or (len(path.split('/'))>=2 and path.split('/')[0]=='usr' and path.split('/')[1] in ('bin','lib','share')),'invalid owned directory')
    for name,record in db['packages'].items():
        fields(record,('sha256','manifest'))
        validate_manifest(record['manifest']);check_profile(record['manifest'],profile)
        require(record['manifest']['id']==name and len(record['sha256'])==64 and all(c in '0123456789abcdef' for c in record['sha256']),'invalid package identity/hash')
    owners(db)
    expected=index_bytes(db)
    require(db['index_sha256']==hashlib.sha256(expected).hexdigest(),'database index binding mismatch')
    view=disk.info(INDEX_PATH)
    require(view is not None and not view['directory'] and view['size']==len(expected),'missing/invalid xypm query index')
    require(disk.export(INDEX_PATH).read_bytes()==expected,'xypm index differs from database')
    return db


def verify_files(disk, db):
    count=0
    for record in db['packages'].values():
        for item in record['manifest']['files']:
            path='/'+item['path'];disk.check_parents(path)
            found=disk.info(path)
            require(found is not None and not found['directory'] and found['size']==item['size'],'installed file missing/type/size changed: '+path)
            require(sha_file(disk.export(path))==item['sha256'],'installed file locally modified: '+path)
            count+=1
    return count


def validate_dependencies(db):
    for name,record in db['packages'].items():
        for dep in record['manifest']['runtime_dependencies']:
            found=db['packages'].get(dep['id'])
            require(found is not None,'missing/reverse dependency: '+name+' -> '+dep['id'])
            require(found['sha256']==dep['sha256'] and found['manifest']['upstream_version']==dep['upstream_version'] and found['manifest']['revision']==dep['revision'],'locked dependency mismatch: '+name+' -> '+dep['id'])
    visiting,done=set(),set()
    def visit(name):
        require(name not in visiting,'dependency cycle')
        if name in done:return
        visiting.add(name)
        for dep in db['packages'][name]['manifest']['runtime_dependencies']:visit(dep['id'])
        visiting.remove(name);done.add(name)
    for name in db['packages']:visit(name)


def regular_image(path):
    path=Path(path)
    require(not path.is_symlink(),'image symlink rejected')
    info=path.stat()
    require(stat.S_ISREG(info.st_mode) and info.st_size>0 and info.st_size%512==0,'expected regular sector-aligned image')
    return path,info


def fd_hash(fd):
    os.lseek(fd,0,os.SEEK_SET);digest=hashlib.sha256()
    while True:
        data=os.read(fd,1<<20)
        if not data:break
        digest.update(data)
    return digest.hexdigest()


def query_image(image, profile, operation='list', package_id=None):
    image,_=regular_image(image)
    with tempfile.TemporaryDirectory(prefix='xypm_query_') as folder, Disk(image,folder,True) as disk:
        db=load_db(disk,profile)
        if operation=='verify-installed':return {'status':'verified','files':verify_files(disk,db)}
        if operation=='info':
            require(package_id in db['packages'],'package not installed')
            return db['packages'][package_id]
        return {'packages':[{'id':name,'upstream_version':r['manifest']['upstream_version'],'revision':r['manifest']['revision'],'sha256':r['sha256']} for name,r in sorted(db['packages'].items())]}


def transact(image, output, profile, operation, package=None, package_id=None, expected_sha256=None, fault_after=None):
    """Explicit candidate export. fault_after is an internal test hook, never a package hook."""
    image,before=regular_image(image);output=Path(output)
    require(not output.exists() and not output.is_symlink(),'output image already exists')
    require(output.resolve()!=image.resolve(),'source and output must differ')
    output.parent.mkdir(parents=True,exist_ok=True)
    helper=host_tool()  # build before locking source; helpers never rebuild shared build/
    fd=os.open(image,os.O_RDWR|getattr(os,'O_NOFOLLOW',0))
    try:
        opened=os.fstat(fd)
        require((opened.st_dev,opened.st_ino)==(before.st_dev,before.st_ino),'image changed before lock')
        fcntl.lockf(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with tempfile.TemporaryDirectory(prefix='.xypm_candidate_',dir=output.parent) as folder:
            folder=Path(folder);candidate=folder/'work.img';stage=folder/'stage';stage.mkdir()
            result=None
            if operation in ('install','upgrade'):
                def sink(event,item,data):
                    dest=stage/item['path']
                    if event=='begin':
                        dest.parent.mkdir(parents=True,exist_ok=True)
                        with dest.open('xb'):pass
                    elif event=='data':
                        with dest.open('ab') as stream:stream.write(data)
                result=verify_package(package,profile,expected_sha256,sink)
                package_id=result['manifest']['id']
            else:require(operation=='remove' and package_id,'unsupported image transaction')
            # Sparse copy from the locked descriptor. No second source open/close, which
            # would release process-associated POSIX record locks on the same inode.
            digest=hashlib.sha256();size=0;os.lseek(fd,0,os.SEEK_SET)
            with candidate.open('xb') as dest:
                while True:
                    data=os.read(fd,1<<20)
                    if not data:break
                    digest.update(data);size+=len(data)
                    if data.count(0)==len(data):dest.seek(len(data),1)
                    else:dest.write(data)
                dest.truncate(size)
            require(size==before.st_size,'source image size changed while copying')
            source_sha=digest.hexdigest();mutations=0
            with Disk(candidate,folder) as disk:
                db=load_db(disk,profile);old=db['packages'].get(package_id)
                require((operation=='install' and old is None) or (operation in ('upgrade','remove') and old is not None),'package already installed or missing; choose explicit install/upgrade/remove')
                # Preserve all locally modified managed files, including unrelated ones.
                verify_files(disk,db)
                ownership=owners(db)
                if operation=='remove':del db['packages'][package_id]
                else:db['packages'][package_id]={'sha256':result['sha256'],'manifest':result['manifest']}
                require(len(db['packages'])<=MAX_PACKAGES,'installed package limit exceeded')
                validate_dependencies(db);owners(db)
                needed=[]
                if result:
                    for item in result['manifest']['files']:
                        path='/'+item['path'];disk.check_parents(path);existing=disk.info(path)
                        require(ownership.get(item['path'].lower()) in (None,package_id),'file owned by another package: '+path)
                        require(existing is None or (ownership.get(item['path'].lower())==package_id and not existing['directory']),'unmanaged file/directory conflict: '+path)
                        needed.append(item)
                    free=disk.command('free');available,cluster=int(free[1]),int(free[2])
                    budget=sum(((x['size']+cluster-1)//cluster)*cluster for x in needed)+(len(needed)*4+32)*cluster+len(canonical(db))
                    require(available>=budget,'insufficient space including database/directory headroom')
                def mutate(*args):
                    nonlocal mutations
                    response=disk.command(*args);mutations+=1
                    if fault_after is not None and mutations>=fault_after:raise RuntimeError('injected candidate failure')
                    return response
                created=set(db['created_directories'])
                if old:
                    for item in old['manifest']['files']:mutate('remove','/'+item['path'])
                def parents(path, track=True):
                    parts=path.strip('/').split('/')
                    for i in range(1,len(parts)):
                        parent='/'.join(parts[:i]);found=disk.info('/'+parent)
                        if found is None:
                            mutate('mkdir','/'+parent)
                            if track:created.add(parent)
                        else:require(found['directory'],'parent file conflict')
                for item in needed:
                    path='/'+item['path'];parents(path)
                    mutate('import',path,confined(stage,item['path']))
                referenced={parent.as_posix() for record in db['packages'].values() for item in record['manifest']['files'] for parent in Path(item['path']).parents if parent.as_posix()!='.'}
                # A nonempty directory (possibly with user files) is kept. Keep its
                # origin record, so a future transaction may clean it only when empty.
                for path in sorted(created-referenced,key=lambda x:-x.count('/')):
                    response=mutate('remove-empty','/'+path)
                    if response==['OK','REMOVED']:created.remove(path)
                    else:require(response==['OK','KEPT'],'unexpected directory cleanup result')
                db['created_directories']=sorted(created)
                view=index_bytes(db);db['index_sha256']=hashlib.sha256(view).hexdigest()
                encoded=canonical(db);require(len(encoded)<=1<<20,'installed database exceeds 1 MiB')
                for path,data in ((DB_PATH,encoded),(INDEX_PATH,view)):
                    parents(path,False)
                    found=disk.info(path)
                    if found:mutate('remove',path)
                    local=folder/('db_write_'+str(mutations));local.write_bytes(data)
                    mutate('import',path,local)
                require(load_db(disk,profile)==db,'database readback differs')
                verified=verify_files(disk,db);disk.command('sync')
            current=os.fstat(fd);named=image.stat()
            require((current.st_size,current.st_mtime_ns,current.st_ctime_ns)==(before.st_size,before.st_mtime_ns,before.st_ctime_ns) and (named.st_dev,named.st_ino)==(before.st_dev,before.st_ino),'source identity/content metadata changed')
            require(fd_hash(fd)==source_sha,'source contents changed during transaction')
            result={'status':'exported_candidate','operation':operation,'id':package_id,
                    'source_sha256':source_sha,'output_sha256':sha_file(candidate),'output':str(output),
                    'verified_files':verified,'mutations':mutations,'backend_sha256':sha_file(helper)}
            # Same-filesystem hard link publishes a complete image without clobber.
            os.link(candidate,output)
            return result
    finally:os.close(fd)
