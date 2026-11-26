# SPDX-License-Identifier: Apache-2.0
"""Rebuild the released P2 xypm transaction code against the qualified glibc SDK."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_xypm import native_glibc_inputs
from xos_app import build, init_project, pack
from xypm_format import canonical, load_json, require, sha_file

P2_RELEASE_BUILD = '6fe330ce2dd9441d72da611c1f87b80dad8e3b03'
GLIBC_TRANSPORT = '7330524046d6e78813f424d9da3799488766036c'


def git_blob(commit, path):
    return subprocess.check_output(['git', 'show', f'{commit}:{path}'], cwd=ROOT)


def replace_once(source, old, new):
    require(source.count(old) == 1, 'historical fixture compatibility edit has changed context')
    return source.replace(old, new, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    profile = load_json(args.profile)
    require(profile.get('runtime_family') == 'glibc', 'a glibc C++ profile is required')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    project = output / 'project'
    init_project(project, 'xos.xypm', 'cpp', profile)
    app = load_json(project / 'xos_app.json')
    app['required_features'].append('stdio_transfer')
    inputs = {}
    for name in ('xypm.cpp', 'xypm_native.hpp', 'xypm_journal.hpp',
                 'xypm_transaction_impl.hpp', 'xypm_recover.cpp'):
        path = 'src/user/programs/' + name
        inputs[name] = git_blob(P2_RELEASE_BUILD, path)
    (output / 'historical_inputs.json').write_bytes(canonical({
        'release_build_commit': P2_RELEASE_BUILD,
        'release_build_recipe_sha256': hashlib.sha256(
            git_blob(P2_RELEASE_BUILD, 'scripts/build_xypm.py')).hexdigest(),
        'release_inputs_sha256': {name: hashlib.sha256(data).hexdigest() for name, data in inputs.items()},
        'glibc_maintenance_client_commit': GLIBC_TRANSPORT,
        'directory_removal_protocol_commit': 'fb5f5331',
    }))
    original = inputs.pop('xypm.cpp')
    legacy_transport = b'// The frozen single-thread SDK uses this weak hook'
    after_transport = b'extern "C" int xypm_recover_run();'
    glue = git_blob(GLIBC_TRANSPORT, 'src/user/programs/xypm.cpp')
    glue = glue.split(b'#ifdef XYP_GLIBC_RUNTIME\n', 1)[1].split(b'#else\n', 1)[0]
    inputs['main.cpp'] = original.split(legacy_transport, 1)[0] + glue + after_transport + original.split(after_transport, 1)[1]

    # FILES B-6 requires an explicit directory removal operation. Preserve the
    # P2 journal and cleanup decisions and use the newer operation at those sites.
    transactions = inputs['xypm_transaction_impl.hpp']
    inputs['xypm_transaction_impl.hpp'] = replace_once(
        transactions, b'files.remove(prep_dir)', b'files.remove_directory(prep_dir)')
    recovery = inputs['xypm_recover.cpp']
    recovery = replace_once(recovery, b'if(s!=state::present||files.remove(path)!=0)return false;',
                            b'if(s!=state::present)return false;'
                            b'if(((attrs&file::stat_is_directory)?files.remove_directory(path):files.remove(path))!=0)return false;')
    recovery = replace_once(recovery, b'if(count||cursor)return true;if(files.remove(path)!=0)',
                            b'if(count||cursor)return true;if(files.remove_directory(path)!=0)')
    inputs['xypm_recover.cpp'] = b'#define XYP_RECOVERY_LIBRARY 1\n' + recovery
    inputs['xypm_profile.hpp'] = (
        '#pragma once\n#include <cstring>\n#define XYP_PACKAGE_PROFILE_ID ' + json.dumps(profile['id'])
        + '\nstatic inline bool xypm_profile_feature(const char* name) {\n'
        + ''.join(f'    if (!std::strcmp(name,{json.dumps(feature)})) return true;\n' for feature in profile['features'])
        + '    return false;\n}\n#define XYP_PACKAGE_FEATURES(name) xypm_profile_feature(name)\n').encode()
    for name in ('text.hpp', 'unicode_width_data.hpp'):
        inputs['xos/' + name] = git_blob(P2_RELEASE_BUILD, 'src/user/include/xos/' + name)
    for relative, source in native_glibc_inputs().items():
        inputs[relative.removeprefix('src/')] = source.read_bytes()
    for name, data in sorted(inputs.items()):
        path = project / 'src' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        if name != 'main.cpp':
            app['files'].append({'source': 'src/' + name, 'path': 'usr/share/xos.xypm/source/' + name,
                                 'role': 'data'})
            if path.suffix == '.cpp':
                app['sources'].append('src/' + name)
    # The historical recipe inherited xos_app's 0.1.0 r0 package identity.
    require((app['upstream_version'], app['revision']) == ('0.1.0', 0), 'historical package identity changed')
    (project / 'xos_app.json').write_bytes(canonical(app))
    receipt = build(project, args.sdk, profile)
    result = pack(project, args.sdk, profile, output / 'xypm.xpk')
    result['elf'] = str(project / receipt['output'])
    result['elf_sha256'] = sha_file(result['elf'])
    (output / 'manifest.json').write_bytes(canonical(result))


if __name__ == '__main__':
    main()
