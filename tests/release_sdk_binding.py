# SPDX-License-Identifier: Apache-2.0
"""Exact release SDK binding, configuration and stale-input rejection; no guest claim."""
import copy,json,shutil,sys,tempfile,unittest,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from sdk_receipt import sha,tree_receipt,verify_sdk,verify_runtime,verify_packaged_sdk,verify_copied_inputs

class BindingCases(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='xos_sdk_binding_');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.sdk=self.root/'sdk';self.sdk.mkdir()
        self.system={'build_id':'fixture-build','configuration':{'architecture':'x86_64','firmware':'bios'},'artifacts':{}}
        for name in ['crt0_posix.o','user.ld','lib/libxos.a','lib/libxos_loader.a','lib/libc.a','lib/libm.a','include/xos/a.hpp']:
            path=self.sdk/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'fixture '+name.encode())
        self.metadata={'build_id':'fixture-build','target':'x86_64-elf','abi':1,'runtime_model':'single','configuration':self.system['configuration']}
        self.write_manifest();self.bind()
    def write_manifest(self):(self.sdk/'manifest.json').write_text(json.dumps(self.metadata))
    def bind(self):
        self.system['artifacts']={'sdk/'+name:{'sha256':value} for name,value in tree_receipt(self.sdk)['files'].items()}
        self.system['sdk_directories']=tree_receipt(self.sdk)['directories']
    def test_exact_input_and_packaged_receipt(self):
        receipt=verify_sdk(self.sdk,self.system);self.assertEqual(receipt['build_id'],'fixture-build')
        release={'sdk_binding':{'packaged':tree_receipt(self.sdk,exclude=('release.json',))}}
        (self.sdk/'release.json').write_text(json.dumps(release));self.assertEqual(verify_packaged_sdk(self.sdk,release),release['sdk_binding']['packaged'])
    def test_changed_file(self):
        (self.sdk/'lib/libc.a').write_bytes(b'wrong archive')
        with self.assertRaises(ValueError):verify_sdk(self.sdk,self.system)
    def test_missing_file(self):
        (self.sdk/'crt0_posix.o').unlink()
        with self.assertRaises(ValueError):verify_sdk(self.sdk,self.system)
    def test_stale_file_and_empty_directory(self):
        for name in ['stale/a.o','empty']:
            with self.subTest(name=name):
                p=self.sdk/name
                if p.suffix:p.parent.mkdir(parents=True);p.write_bytes(b'stale')
                else:p.mkdir()
                with self.assertRaises(ValueError):verify_sdk(self.sdk,self.system)
                if p.is_file():p.unlink();p.parent.rmdir()
                else:p.rmdir()
    def test_mixed_manifest_and_symlink(self):
        self.metadata['build_id']='another-build';self.write_manifest()
        with self.assertRaises(ValueError):verify_sdk(self.sdk,self.system)
        self.metadata['build_id']='fixture-build';self.write_manifest()
        (self.sdk/'alias').symlink_to(self.sdk/'manifest.json')
        with self.assertRaises(ValueError):verify_sdk(self.sdk,self.system)
    def test_wrong_config_target_or_runtime_even_when_file_hash_is_rebound(self):
        for field,value in [('configuration',{'firmware':'uefi'}),('target','aarch64-elf'),('abi',2),('runtime_model','threaded'),('build_id','wrong')]:
            with self.subTest(field=field):
                old=self.metadata[field];self.metadata[field]=value;self.write_manifest();self.bind()
                with self.assertRaises(ValueError):verify_sdk(self.sdk,self.system)
                self.metadata[field]=old
    def test_unbound_legacy_system_refused(self):
        self.system['artifacts']={}
        with self.assertRaises(ValueError):verify_sdk(self.sdk,self.system)
    def test_packager_rejects_bad_sdk_before_creating_output(self):
        parent=ROOT/'build/releases';parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='audit_binding_',dir=parent) as folder:
            out=Path(folder);shutil.copytree(self.sdk,out/'sdk')
            boot=out/'xos.img';boot.write_bytes(b'fixture boot bytes')
            system=copy.deepcopy(self.system);system['artifacts']['xos.img']={'sha256':sha(boot)}
            (out/'system_manifest.json').write_text(json.dumps(system))
            (out/'sdk/lib/libc.a').write_bytes(b'wrong SDK')
            before={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()}
            run=subprocess.run([sys.executable,str(ROOT/'scripts/package_release.py'),'--release-dir',str(out),
                                '--dash-manifest',str(out/'unused.json')],capture_output=True,text=True)
            self.assertNotEqual(run.returncode,0);self.assertIn('SDK file set',run.stderr)
            after={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()}
            self.assertEqual(before,after)
            self.assertEqual({p.name for p in out.iterdir()},{'sdk','xos.img','system_manifest.json'})
    def test_runtime_tree_and_provenance_binding(self):
        runtime=self.root/'runtime';(runtime/'lib').mkdir(parents=True)
        lib=runtime/'lib/libstdc++.a';lib.write_bytes(b'fixture library')
        manifest={'archives':[{'root':'runtime','path':'lib/libstdc++.a','sha256':sha(lib)}]}
        (runtime/'manifest.json').write_text(json.dumps(manifest))
        lock={'tree_sha256':tree_receipt(runtime)['tree_sha256'],'manifest_sha256':sha(runtime/'manifest.json'),'scope':'fixture'}
        verify_runtime(runtime,lock)
        lib.write_bytes(b'wrong')
        with self.assertRaises(ValueError):verify_runtime(runtime,lock)
    def test_copy_must_match_inputs_before_publication(self):
        sdk_input=verify_sdk(self.sdk,self.system)
        runtime={'files':{'manifest.json':'0'*64}}
        (self.sdk/'target_runtime_provenance.json').write_bytes(b'wrong provenance')
        with self.assertRaises(ValueError):verify_copied_inputs(self.sdk,sdk_input,runtime)
        (self.sdk/'lib/libc.a').write_bytes(b'wrong SDK')
        with self.assertRaises(ValueError):verify_copied_inputs(self.sdk,sdk_input,{'files':{}})
    def test_packaged_tamper_refused(self):
        release={'sdk_binding':{'packaged':tree_receipt(self.sdk,exclude=('release.json',))}}
        (self.sdk/'user.ld').write_bytes(b'wrong')
        with self.assertRaises(ValueError):verify_packaged_sdk(self.sdk,release)

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(BindingCases))
    out=ROOT/'build/audit_01';out.mkdir(parents=True,exist_ok=True)
    (out/'sdk_binding_tests.json').write_text(json.dumps({'status':'passed' if result.wasSuccessful() else 'failed','tests':result.testsRun,'scope':'host identity binding fixtures, not guest qualification'},indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
