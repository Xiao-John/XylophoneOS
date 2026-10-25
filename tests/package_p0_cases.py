# SPDX-License-Identifier: Apache-2.0
"""P0 adversarial package tests and real independent C/C++ SDK builds."""
import argparse
import copy
import hashlib
import io
import json
from pathlib import Path
import shutil
import struct
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from xpkg_format import (DEFAULT_PROFILE, PackageError, canonical, check_profile, load_json,
                         inspect_elf, pack_package, sha_file, strict_json, validate_manifest,
                         verify_package)
from xos_app import build, check, init_project, pack, sdk_check

SDK = ROOT / 'build/releases/0.0.1-1024/xylophoneos_revival_0.0.1-1024_sdk'
PROFILE = load_json(DEFAULT_PROFILE)
REPORT = ROOT / 'build/package_p0/host_report.json'


class PackageCases(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='xos_package_case_')
        self.root = Path(self.folder.name)
        receipt = b'{"status":"fixture_not_built"}\n'
        files = {'usr/share/test/data.txt': '木琴🎵\n'.encode(),
                 'usr/share/test/LICENSE': b'fixture license\n',
                 'usr/share/test/receipt.json': receipt}
        for name, body in files.items():
            dest = self.root / name; dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(body)
        self.manifest = {'format_version':1,'id':'friends.test','upstream_version':'1.0','revision':0,
                         'target_profile':PROFILE['id'],'required_features':[], 'runtime_dependencies':[],
                         'files':[{'path':name,'type':'file','size':len(body),'sha256':hashlib.sha256(body).hexdigest(),'role':'data'} for name,body in files.items()],
                         'licenses':['usr/share/test/LICENSE'],
                         'build_receipt':{'path':'usr/share/test/receipt.json','sha256':hashlib.sha256(receipt).hexdigest()},
                         'source':'local fixture; not an authenticity claim'}

    def tearDown(self):
        self.folder.cleanup()

    def tar(self, manifest=None, changes=None):
        manifest = manifest or self.manifest
        out = self.root / 'custom.xpk'
        with tarfile.open(out,'w',format=tarfile.USTAR_FORMAT) as tar:
            members = [('manifest.json',canonical(manifest))] + [('payload/'+x['path'],(self.root/x['path']).read_bytes()) for x in self.manifest['files']]
            if changes:
                members = changes(members)
            for name,body in members:
                info=tarfile.TarInfo(name);info.size=len(body)
                tar.addfile(info,io.BytesIO(body))
        return out

    def test_roundtrip_utf8_and_deterministic(self):
        one, two = self.root/'one.xpk', self.root/'two.xpk'
        first=pack_package(self.root,self.manifest,one)
        second=pack_package(self.root,self.manifest,two)
        self.assertEqual(first['sha256'],second['sha256'])
        verified=verify_package(one,PROFILE,first['sha256'])
        self.assertEqual(verified['payload_files'],3)

    def test_bad_expected_hash(self):
        with self.assertRaises(PackageError):verify_package(self.tar(),expected_sha256='0'*64)

    def test_profile_and_feature_refused(self):
        manifest=copy.deepcopy(self.manifest);manifest['target_profile']='wrong-profile'
        with self.assertRaises(PackageError):check_profile(manifest,PROFILE)
        manifest['target_profile']=PROFILE['id'];manifest['required_features']=['threads']
        with self.assertRaises(PackageError):check_profile(manifest,PROFILE)

    def test_json_duplicates_nan_surrogates_depth(self):
        for data in (b'{"id":1,"id":2}',b'{"x":NaN}',b'{"x":"\\ud800"}',b'['*10+b'0'+b']'*10,b'{"x":1.5}'):
            with self.subTest(data=data),self.assertRaises(PackageError):strict_json(data)

    def test_traversal_case_alias_reserved_paths(self):
        for path in ('/usr/bin/a','usr/bin/../a','usr/bin/A~1','usr/share/XOS23.TMP',
                     'usr/share/a.','usr/share/中文','usr//bin/a','etc/a','usr/share/a\\b'):
            manifest=copy.deepcopy(self.manifest);manifest['files'][0]['path']=path
            with self.subTest(path=path),self.assertRaises(PackageError):validate_manifest(manifest)

    def test_case_and_parent_file_collisions(self):
        for name in ('usr/share/TEST/data.txt','usr/share/test'):
            manifest=copy.deepcopy(self.manifest)
            item=copy.deepcopy(manifest['files'][0]);item['path']=name;manifest['files'].append(item)
            with self.subTest(name=name),self.assertRaises(PackageError):validate_manifest(manifest)

    def test_metadata_bounds_unknown_and_types(self):
        for key,value in (('revision',True),('format_version',2),('unknown',1)):
            manifest=copy.deepcopy(self.manifest);manifest[key]=value
            with self.subTest(key=key),self.assertRaises(PackageError):validate_manifest(manifest)
        manifest=copy.deepcopy(self.manifest);manifest['files'][0]['size']=67108865
        with self.assertRaises(PackageError):validate_manifest(manifest)

    def test_license_receipt_and_dependencies(self):
        for key,value in (('licenses',[]),('build_receipt',{'path':'usr/share/test/receipt.json','sha256':'0'*64}),
                          ('runtime_dependencies',[{'id':'friends.test','upstream_version':'1','revision':0,'sha256':'0'*64}])):
            manifest=copy.deepcopy(self.manifest);manifest[key]=value
            with self.subTest(key=key),self.assertRaises(PackageError):validate_manifest(manifest)

    def test_missing_extra_duplicate_or_manifest_order(self):
        changes=(lambda x:x[:-1],lambda x:x+[('payload/usr/share/test/extra',b'')],
                 lambda x:x+[x[1]],lambda x:x[1:]+x[:1])
        for change in changes:
            with self.subTest(change=change),self.assertRaises(PackageError):verify_package(self.tar(changes=change))

    def test_payload_corruption_truncation_and_trailing(self):
        data=self.tar().read_bytes()
        pos=data.index('木琴🎵'.encode())
        corrupted=bytearray(data);corrupted[pos]^=1
        for body in (bytes(corrupted),data[:1000],data+b'x'*512,data+b'\0'):
            (self.root/'bad.xpk').write_bytes(body)
            with self.subTest(length=len(body)),self.assertRaises(PackageError):verify_package(self.root/'bad.xpk')

    def test_links_extensions_and_bad_checksum(self):
        data=bytearray(self.tar().read_bytes())
        for typ in (b'2',b'1',b'x',b'L',b'5'):
            bad=bytearray(data);bad[156:157]=typ;bad[148:156]=b' '*8
            bad[148:156]=(('%06o'%sum(bad[:512])).encode()+b'\0 ')
            path=self.root/'bad.xpk';path.write_bytes(bad)
            with self.subTest(type=typ),self.assertRaises(PackageError):verify_package(path)
        data[100]^=1;(self.root/'bad.xpk').write_bytes(data)
        with self.assertRaises(PackageError):verify_package(self.root/'bad.xpk')

    def test_no_clobber_and_partial_cleanup(self):
        out=self.root/'out.xpk';out.write_bytes(b'preserve')
        with self.assertRaises(FileExistsError):pack_package(self.root,self.manifest,out)
        self.assertEqual(out.read_bytes(),b'preserve')
        out.unlink();(self.root/'usr/share/test/data.txt').write_bytes(b'changed')
        with self.assertRaises(PackageError):pack_package(self.root,self.manifest,out)
        self.assertFalse(out.exists())

    def test_symlink_source_and_package(self):
        source=self.root/'usr/share/test/data.txt';source.unlink();source.symlink_to(self.root/'usr/share/test/LICENSE')
        with self.assertRaises(PackageError):pack_package(self.root,self.manifest,self.root/'out.xpk')
        link=self.root/'package_link';link.symlink_to(self.tar())
        with self.assertRaises(PackageError):verify_package(link)

    def test_executable_role_requires_supported_elf(self):
        manifest=copy.deepcopy(self.manifest);manifest['files'][0]['role']='executable'
        with self.assertRaises(PackageError):verify_package(self.tar(manifest))


class IndependentBuildCases(unittest.TestCase):
    def test_real_c_cpp_project_outside_repository(self):
        results=[]
        with tempfile.TemporaryDirectory(prefix='xos_independent_apps_') as folder:
            base=Path(folder)
            self.assertFalse(base.is_relative_to(ROOT))
            for language in ('c','cpp'):
                project=base/language
                init_project(project,'friends.external_'+language,language,PROFILE)
                result=build(project,SDK,PROFILE)
                check(project,SDK,PROFILE)
                self.assertEqual(result['status'],'cross_built_guest_not_run')
                first=pack(project,SDK,PROFILE,base/(language+'.xpk'))
                again=pack(project,SDK,PROFILE,base/(language+'_again.xpk'))
                self.assertEqual(first['sha256'],again['sha256'])
                verified=verify_package(base/(language+'.xpk'),PROFILE)
                # Keep new P0 artifacts, not the temporary source directory.
                artifacts=REPORT.parent/language;artifacts.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(project/result['output'],artifacts/'app.elf')
                shutil.copyfile(base/(language+'.xpk'),artifacts/'app.xpk')
                (artifacts/'build_receipt.json').write_bytes(canonical(result))
                self.assertGreater(len(verified['manifest']['licenses']),1)
                results.append({'language':language,'package_sha256':first['sha256'],'elf_sha256':result['output_sha256'],'files':first['files']})
                source=project/('src/main.'+('c' if language=='c' else 'cpp'))
                source.write_text(source.read_text()+'\n/* changed */\n')
                with self.assertRaises(PackageError):check(project,SDK,PROFILE)
                with self.assertRaises(PackageError):pack(project,SDK,PROFILE,base/'stale.xpk')
                self.assertFalse((base/'stale.xpk').exists())
                # The wrong machine and unsupported dynamic headers must be rejected.
                binary=bytearray((project/result['output']).read_bytes());struct.pack_into('<H',binary,18,183)
                (base/'wrong.elf').write_bytes(binary)
                with self.assertRaises(PackageError):inspect_elf(base/'wrong.elf')
                original=(project/result['output']).read_bytes()
                phoff=struct.unpack_from('<Q',original,32)[0]
                for offset,fmt,bad in ((24,'<Q',0),(phoff,'<I',2),(phoff+4,'<I',7),
                                       (phoff+16,'<Q',0x60000000),(phoff+48,'<Q',3)):
                    binary=bytearray(original);struct.pack_into(fmt,binary,offset,bad)
                    (base/'wrong.elf').write_bytes(binary)
                    with self.subTest(field=offset),self.assertRaises(PackageError):inspect_elf(base/'wrong.elf')
            report={'status':'passed','scope':'host_build_package_only','profile':PROFILE['id'],'sdk_tree_sha256':PROFILE['sdk_tree_sha256'][0],'independent_projects':results,'guest':'not_run'}
            REPORT.write_bytes(canonical(report))

    def test_sdk_binding_and_init_refusal(self):
        profile=copy.deepcopy(PROFILE);profile['sdk_tree_sha256']=['0'*64]
        with self.assertRaises(PackageError):sdk_check(SDK,profile)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(FileExistsError):init_project(folder,'friends.keep','c',PROFILE)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--sdk',type=Path,default=SDK);parser.add_argument('--output',type=Path,default=REPORT)
    args=parser.parse_args();SDK=args.sdk.resolve();REPORT=args.output.resolve();REPORT.parent.mkdir(parents=True,exist_ok=True)
    suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(PackageCases),unittest.defaultTestLoader.loadTestsFromTestCase(IndependentBuildCases)])
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if REPORT.exists():
        report=json.loads(REPORT.read_text());report['tests_run']=result.testsRun
        report['status']='passed' if result.wasSuccessful() else 'failed';report['failures']=len(result.failures);report['errors']=len(result.errors)
        REPORT.write_bytes(canonical(report))
    raise SystemExit(0 if result.wasSuccessful() else 1)
