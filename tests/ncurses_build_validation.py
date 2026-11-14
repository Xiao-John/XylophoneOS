#!/usr/bin/env python3
"""Host regression checks for ncurses SDK isolation and header staging."""
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from xos_app import tree_receipt


class ncurses_build_validation(unittest.TestCase):
    def test_sdk_isolation_and_package_header(self):
        spec = importlib.util.spec_from_file_location('ncurses_build', ROOT / 'src/ports/ncurses/build.py')
        recipe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(recipe)
        for fail in (False, True):
            for existing_stub in (False, True):
                with self.subTest(fail=fail, existing_stub=existing_stub), tempfile.TemporaryDirectory() as temp:
                    root = Path(temp)
                    sdk = root / 'sdk'
                    (sdk / 'include').mkdir(parents=True)
                    for name in ('manifest.json', 'user.ld', 'crt0_posix.o'):
                        (sdk / name).write_text('synthetic SDK input')
                    if existing_stub:
                        (sdk / 'include/sgtty.h').write_text('#error SDK stub must not be used\n')
                    before = tree_receipt(sdk)
                    source = root / 'ncurses-6.5'
                    (source / 'include').mkdir(parents=True)
                    (source / 'configure').touch()
                    (source / 'include/term.h').write_text('#include <sgtty.h>\n')
                    archive = root / 'source.tar'
                    with tarfile.open(archive, 'w') as tar:
                        tar.add(source, arcname=source.name)
                    here = root / 'src/ports/ncurses'
                    shutil.copytree(recipe.HERE, here)
                    lock = json.loads((here / 'source_lock.json').read_text())
                    lock['sha256'] = recipe.sha256(archive)
                    (here / 'source_lock.json').write_text(json.dumps(lock))
                    consumers = root / 'tests/fixtures/ncursesw'
                    consumers.mkdir(parents=True)
                    for name in ('wide_screen_probe', 'reentry_probe'):
                        (consumers / (name + '.c')).touch()
                    out = root / 'out'
                    stub_bytes = []

                    def run(command, cwd=None, env=None):
                        if str(command[0]).endswith('/configure'):
                            flags = shlex.split(env['CPPFLAGS'])
                            compat = Path(flags[flags.index('-I') + 1])
                            stub_bytes.append((compat / 'sgtty.h').read_bytes())
                            self.assertIn(str(compat), shlex.split(env['CFLAGS']))
                        elif command[0] == 'make':
                            if fail:
                                raise subprocess.CalledProcessError(2, command)
                            (cwd / 'lib').mkdir()
                            (cwd / 'lib/libncursesw.a').write_bytes(b'synthetic library')
                        elif command[0] == 'objcopy':
                            shutil.copyfile(command[-2], command[-1])
                        elif '-o' in command and command[0] == 'cc':
                            Path(command[-1]).write_bytes(b'synthetic consumer')

                    def pack(tree, manifest, output):
                        header = 'usr/share/ncursesw/include/sgtty.h'
                        self.assertEqual((tree / header).read_bytes(), stub_bytes[0])
                        entry = next(item for item in manifest['files'] if item['path'] == header)
                        self.assertEqual(entry['sha256'], recipe.sha256(tree / header))
                        # Resolve term.h's dependency with only the staged include directory.
                        subprocess.run(['cc', '-nostdinc', '-fsyntax-only', '-x', 'c',
                                        '-I', str(tree / 'usr/share/ncursesw/include'),
                                        str(tree / 'usr/share/ncursesw/include/term.h')], check=True)
                        output.touch()
                        return {'sha256': '0' * 64, 'payload_files': len(manifest['files'])}

                    env = {'XOS_SDK': str(sdk), 'XOS_SOURCE_ARCHIVE': str(archive), 'XOS_OUT': str(out)}
                    with patch.dict(os.environ, env), patch.object(recipe, 'HERE', here), \
                            patch.object(recipe.shutil, 'which', side_effect=lambda name: {'x86_64-elf-objcopy': 'objcopy', 'tic': 'tic'}.get(name, 'cc')), \
                            patch.object(recipe.subprocess, 'check_output', return_value='synthetic\n'), \
                            patch.object(recipe, 'run', side_effect=run), \
                            patch('xypm_format.pack_package', side_effect=pack) as packer:
                        if fail:
                            with self.assertRaises(subprocess.CalledProcessError):
                                recipe.main()
                            packer.assert_not_called()
                        else:
                            recipe.main()
                            packer.assert_called_once()
                            receipt = json.loads((out / 'build_receipt.json').read_text())
                            self.assertEqual(receipt['sdk']['sdk_tree_sha256'], before[0])
                    self.assertEqual(tree_receipt(sdk), before)
                    self.assertFalse(list(out.glob('ncursesw_build_*')))


if __name__ == '__main__':
    unittest.main()
