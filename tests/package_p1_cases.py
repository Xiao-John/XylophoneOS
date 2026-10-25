# SPDX-License-Identifier: Apache-2.0
"""P1 candidate-image transactions: ownership, dependencies, failure/source preservation."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from make_work_disk import make_image
from xypm_format import DEFAULT_PROFILE,PackageError,canonical,load_json,pack_package,sha_file
from xypm_image import Disk,DB_PATH,INDEX_PATH,transact,query_image
PROFILE=load_json(DEFAULT_PROFILE)
REPORT=ROOT/'build/package_p1/host_report.json'


class ImageCases(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='xypm_p1_case_');self.root=Path(self.temp.name)
        self.source=self.root/'source.img';self.source.write_bytes(make_image())
        self.serial=0

    def tearDown(self):self.temp.cleanup()

    def package(self,name='friends.alpha',revision=0,body=b'alpha\n',deps=None,destination=None,version='1.0'):
        self.serial+=1;stage=self.root/('stage_'+str(self.serial));stage.mkdir()
        files={destination or 'usr/share/'+name+'/data.txt':body,
               'usr/share/licenses/'+name+'/LICENSE':b'fixture Apache-2.0 notice\n',
               'usr/share/'+name+'/build_receipt.json':b'{"status":"fixture"}\n'}
        entries=[]
        for path,data in files.items():
            p=stage/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
            entries.append({'path':path,'type':'file','size':len(data),'sha256':hashlib.sha256(data).hexdigest(),'role':'data'})
        manifest={'format_version':1,'id':name,'upstream_version':version,'revision':revision,'target_profile':PROFILE['id'],
                  'required_features':[],'runtime_dependencies':deps or [],'files':entries,
                  'licenses':['usr/share/licenses/'+name+'/LICENSE'],
                  'build_receipt':{'path':'usr/share/'+name+'/build_receipt.json','sha256':hashlib.sha256(files['usr/share/'+name+'/build_receipt.json']).hexdigest()},
                  'source':'test fixture, not an executable'}
        output=self.root/('package_'+str(self.serial)+'.xpk');pack_package(stage,manifest,output);return output

    def transaction(self,source,operation,package=None,name=None,**kwargs):
        self.serial+=1;output=self.root/('result_'+str(self.serial)+'.img')
        result=transact(source,output,PROFILE,operation,package=package,package_id=name,**kwargs)
        return output,result

    def assert_preserved_failure(self,source,operation,package=None,name=None,kind=ValueError,**kwargs):
        before=sha_file(source);self.serial+=1;output=self.root/('failure_'+str(self.serial)+'.img')
        with self.assertRaises(kind):transact(source,output,PROFILE,operation,package=package,package_id=name,**kwargs)
        self.assertEqual(sha_file(source),before);self.assertFalse(output.exists())

    def test_install_upgrade_remove_and_utf8_metadata(self):
        original=sha_file(self.source)
        installed,receipt=self.transaction(self.source,'install',self.package(version='木琴 1.0'))
        self.assertEqual(sha_file(self.source),original)
        self.assertEqual(query_image(installed,PROFILE)['packages'][0]['upstream_version'],'木琴 1.0')
        self.assertEqual(query_image(installed,PROFILE,'verify-installed')['files'],3)
        upgraded,_=self.transaction(installed,'upgrade',self.package(revision=1,body=b'new\n'))
        self.assertEqual(query_image(upgraded,PROFILE,'info','friends.alpha')['manifest']['revision'],1)
        removed,_=self.transaction(upgraded,'remove',name='friends.alpha')
        self.assertEqual(query_image(removed,PROFILE)['packages'],[])
        self.assertGreater(receipt['mutations'],0)

    def test_unmanaged_and_case_folded_collision(self):
        p=self.root/'original';p.write_bytes(b'user original')
        with Disk(self.source,self.root) as disk:
            for name in ('/usr','/usr/share','/usr/share/friends.alpha'):disk.command('mkdir',name)
            disk.command('import','/usr/share/friends.alpha/DATA.txt',p)
        self.assert_preserved_failure(self.source,'install',self.package())

    def test_owned_conflict_and_parent_file(self):
        installed,_=self.transaction(self.source,'install',self.package(destination='usr/share/shared/file'))
        self.assert_preserved_failure(installed,'install',self.package('friends.other',destination='usr/share/shared/file'))
        self.assert_preserved_failure(installed,'install',self.package('friends.other',destination='usr/share/shared/file/child'))

    def test_modified_files_protected_for_upgrade_and_remove(self):
        installed,_=self.transaction(self.source,'install',self.package())
        changed=self.root/'changed';changed.write_bytes(b'user changes\n')
        with Disk(installed,self.root) as disk:
            disk.command('remove','/usr/share/friends.alpha/data.txt')
            disk.command('import','/usr/share/friends.alpha/data.txt',changed)
        self.assert_preserved_failure(installed,'upgrade',self.package(revision=1))
        self.assert_preserved_failure(installed,'remove',name='friends.alpha')
        with self.assertRaises(PackageError):query_image(installed,PROFILE,'verify-installed')

    def test_exact_dependencies_and_reverse_dependency(self):
        base=self.package();dependency={'id':'friends.alpha','upstream_version':'1.0','revision':0,'sha256':sha_file(base)}
        dependent=self.package('friends.beta',deps=[dependency])
        self.assert_preserved_failure(self.source,'install',dependent)
        installed,_=self.transaction(self.source,'install',base)
        both,_=self.transaction(installed,'install',dependent)
        self.assertEqual(len(query_image(both,PROFILE)['packages']),2)
        self.assert_preserved_failure(both,'remove',name='friends.alpha')
        self.assert_preserved_failure(both,'upgrade',self.package(revision=1))
        only,_=self.transaction(both,'remove',name='friends.beta')
        empty,_=self.transaction(only,'remove',name='friends.alpha')
        self.assertFalse(query_image(empty,PROFILE)['packages'])

    def test_injected_failure_never_publishes_or_changes_source(self):
        package=self.package();_,receipt=self.transaction(self.source,'install',package)
        for step in (1,5,receipt['mutations']-1,receipt['mutations']):
            with self.subTest(step=step):self.assert_preserved_failure(self.source,'install',package,kind=RuntimeError,fault_after=step)

    def test_output_refusal_symlinks_and_image_lock(self):
        package=self.package()
        with self.assertRaises(PackageError):transact(self.source,self.source,PROFILE,'install',package=package)
        link=self.root/'alias.img';link.symlink_to(self.source)
        self.assert_preserved_failure(link,'install',package)
        # Another process holds the same POSIX image record lock used by QEMU/bridge.
        code="import fcntl,sys; f=open(sys.argv[1],'r+b'); fcntl.lockf(f,fcntl.LOCK_EX); print('locked',flush=True); sys.stdin.read()"
        proc=subprocess.Popen([sys.executable,'-c',code,str(self.source)],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
        try:
            self.assertEqual(proc.stdout.readline(),b'locked\n')
            self.assert_preserved_failure(self.source,'install',package,kind=OSError)
        finally:proc.stdin.close();proc.wait();proc.stdout.close()

    def test_corrupt_database_or_projection_refused(self):
        installed,_=self.transaction(self.source,'install',self.package())
        with Disk(installed,self.root) as disk:
            changed=self.root/'bad';changed.write_bytes(b'xypm-index-v1\ncorrupt\n')
            disk.command('remove',INDEX_PATH);disk.command('import',INDEX_PATH,changed)
        with self.assertRaises(PackageError):query_image(installed,PROFILE)
        self.assert_preserved_failure(installed,'remove',name='friends.alpha')

    def test_legacy_database_not_mistaken_for_empty_installation(self):
        legacy=self.root/'legacy';legacy.write_bytes(b'legacy fixture\n')
        for old_name in ('xpm','xpkg'):
            for leaf in ('db.json','index.tsv'):
                with self.subTest(name=old_name,leaf=leaf):
                    image=self.root/(old_name+'_'+leaf+'.img');shutil.copyfile(self.source,image)
                    with Disk(image,self.root) as disk:
                        for path in ('/var','/var/lib','/var/lib/'+old_name):disk.command('mkdir',path)
                        disk.command('import','/var/lib/'+old_name+'/'+leaf,legacy)
                    with self.assertRaisesRegex(PackageError,'legacy package database'):query_image(image,PROFILE)
                    self.assert_preserved_failure(image,'install',self.package())

    def test_full_disk_preflight(self):
        large=self.package(body=b'A'*(17<<20))
        self.assert_preserved_failure(self.source,'install',large)

    def test_user_files_in_shared_directory_survive_uninstall(self):
        installed,_=self.transaction(self.source,'install',self.package())
        local=self.root/'user';local.write_bytes(b'user save\n')
        with Disk(installed,self.root) as disk:disk.command('import','/usr/share/friends.alpha/user_save',local)
        removed,_=self.transaction(installed,'remove',name='friends.alpha')
        with Disk(removed,self.root,True) as disk:
            self.assertEqual(disk.export('/usr/share/friends.alpha/user_save').read_bytes(),b'user save\n')
        self.assertFalse(query_image(removed,PROFILE)['packages'])

    def test_exports_across_sessions_do_not_collide(self):
        installed,_=self.transaction(self.source,'install',self.package())
        with Disk(installed,self.root,True) as disk:first=disk.export(DB_PATH)
        before=first.read_bytes()
        with Disk(installed,self.root,True) as disk:second=disk.export(DB_PATH)
        self.assertNotEqual(first,second)
        self.assertEqual(second.read_bytes(),before)
        self.assertEqual(first.read_bytes(),before)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path,default=REPORT);args=parser.parse_args()
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(ImageCases)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    report={'status':'passed' if result.wasSuccessful() else 'failed','tests_run':result.testsRun,
            'failures':len(result.failures),'errors':len(result.errors),'scope':'P1 host candidate images only','guest':'not_run'}
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_bytes(canonical(report))
    raise SystemExit(0 if result.wasSuccessful() else 1)
