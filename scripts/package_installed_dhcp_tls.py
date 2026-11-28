#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compose one explicitly named DHCP/TLS installation through an offline XPK transaction.

The supported installation topology is an ordinary boot ISO plus a persistent
FAT disk. This tool installs the complete approved dynamic closure, controller,
trust snapshots and deployment record into the disk. It does not claim a BIOS
hard-disk boot path or change the default release configuration.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

repository_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repository_root / 'tests'))
from build_dynamic_program import inspect_native_sdk
from make_work_disk import create_fat32
from shell_launch_support import bind_system
from xypm_format import canonical, pack_package, require, sha_file, verify_package
from xypm_image import query_image, transact
from xypm_sdk_profile import inspect_sdk, relative_file, verify_profile
from verify_installed_runtime import verify as verify_runtime_binding

package_prefix = 'usr/share/xos/p1_k4'
application_name = 'installed_dhcp_tls'


def load(path):
    return json.loads(path.read_bytes())


def compose(args):
    system, program, launcher, runtime, certs = (
        getattr(args, name).resolve(strict=True) for name in ('system', 'program', 'launcher', 'runtime', 'certificates'))
    out = args.output.absolute()
    out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'topology': 'ordinary_boot_ISO_and_XPK_installed_persistent_FAT',
              'configuration': 'p1_k4_installed_dhcp_tls_v1', 'guest_qualification': 'not_run'}
    try:
        system_manifest = bind_system(system, args.system_source)
        app = load(program / 'manifest.json')
        controller = load(launcher / 'receipt.json')
        gnu = load(runtime / 'manifest.json')
        native = inspect_native_sdk(system / 'sdk')
        runtime_binding = verify_runtime_binding(runtime, args.runtime_source_revision,
                                                args.system_source, system / 'sdk')
        c_binding = inspect_sdk('glibc', runtime / 'sdk_snapshot')['binding']
        require(app['status'] == controller['status'] == 'built_not_run' and app['name'] == application_name,
                'selected application/controller must be the built installed fixture')
        require(gnu['status'] == 'public_runtime_built_not_run' and app['sdk_binding'] == c_binding == gnu['sdk_binding']
                and app['native_sdk_binding'] == native and controller['c_sdk_binding'] == c_binding
                and controller['native_system_manifest_sha256'] == sha_file(system / 'manifest.json'),
                'application/runtime/controller/installation bindings differ')
        for path, expected in gnu['artifacts'].items():
            require(sha_file(relative_file(runtime, path)) == expected, 'runtime artifact changed: ' + path)
        for path, expected in controller['artifacts'].items():
            require(sha_file(relative_file(launcher, path)) == expected, 'controller artifact changed: ' + path)
        policy = repository_root / 'tests/fixtures/network/installed_dhcp_tls_profile.json'
        network = load(system / 'net_lwip_inputs.json')
        expected_policy = load(policy)
        require(network.get('dhcp_profile') == dict(expected_policy, source_sha256=sha_file(policy))
                and not network.get('static_profile') and not network.get('dns_probe'),
                'system is not the sealed installed DHCP/TLS profile')
        parent_profile = load(args.profile)
        parent_verified = verify_profile(parent_profile, 'glibc', runtime / 'sdk_snapshot')
        require(all(parent_profile['sdk_binding'][key] == c_binding[key]
                    for key in ('sdk_manifest_sha256', 'sdk_tree_sha256')),
                'parent package profile differs from the complete C SDK anchors')
        composition = {'configuration': report['configuration'], 'parent_profile': parent_profile['id'],
            'parent_profile_sha256': sha_file(args.profile), 'parent_profile_verification': parent_verified,
            'system_build_id': system_manifest['build_id'],
            'system_manifest_sha256': sha_file(system / 'manifest.json'),
            'ordinary_iso_sha256': sha_file(system / 'xos-install.iso'),
            'runtime_source_binding': runtime_binding,
            'bootstrap_policy_sha256': sha_file(policy), 'runtime_manifest_sha256': sha_file(runtime / 'manifest.json'),
            'application_manifest_sha256': sha_file(program / 'manifest.json'),
            'controller_receipt_sha256': sha_file(launcher / 'receipt.json'),
            'native_abi': app['native_abi'], 'c_sdk_binding': c_binding, 'native_sdk_binding': native,
            'generation': app['generation'], 'trust': load(certs / 'certificates.json')['public_files']}
        composition['dynamic_thread_scope'] = 'main_thread; pthread_create=ENOTSUP_without_libgcc_s'
        profile = dict(parent_profile, id='xos-x86_64-glibc-k4-dhcp-tls-' + hashlib.sha256(canonical(composition)).hexdigest()[:12],
            status='combined_candidate_guest_not_run', layout='public_fixed_dynamic_startup_v2',
            runtime_model='main_thread_fixed_closure',
            features=[name for name in parent_profile['features'] if name not in ('threads', 'cxx_runtime')],
            verified_system_builds=[], composition=composition)
        (out / 'profile.json').write_bytes(canonical(profile))
        root = out / 'payload'
        root.mkdir()
        files = {}

        def add(path, source, role='data', expected=None):
            require(path.startswith('usr/'), 'installed XPK path must use a managed root')
            if expected:
                require(sha_file(source) == expected, 'selected input artifact changed: ' + path)
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            require(sha_file(source) == sha_file(target), 'input changed while installing candidate')
            files[path] = {'path': path, 'type': 'file', 'size': target.stat().st_size,
                           'sha256': sha_file(target), 'role': role}

        for guest, entry in app['files'].items():
            add(guest.lstrip('/'), relative_file(program, entry['local']), expected=entry['sha256'])
        generation = app['generation']
        add(generation['guest'].lstrip('/'), relative_file(program, generation['local']), expected=generation['sha256'])
        approved = controller['approved_generations']
        require(len(approved) == 1 and approved[0]['sha256'] == generation['sha256']
                and approved[0]['manifest'] == generation['guest'], 'controller approved a different generation')
        add('usr/bin/k4_dynamic_run', launcher / 'dynamic-run.elf', 'executable', controller['artifacts']['dynamic-run.elf'])
        for number in (1, 2):
            name = f'roots-{number}.bin'
            add(package_prefix + '/' + name, certs / name, expected=composition['trust'][name])
        add(package_prefix + '/bootstrap_dhcp.json', policy)
        add(package_prefix + '/profile.json', out / 'profile.json')
        license_sources = {'APACHE-2.0.txt': repository_root / 'LICENSE', 'MIT-legacy.txt': repository_root / 'licenses/mit_legacy.txt',
            'glibc-COPYING.LIB': runtime / 'sdk_snapshot/sysroot/usr/share/xos-glibc/COPYING.LIB',
            'glibc-LICENSES': runtime / 'sdk_snapshot/sysroot/usr/share/xos-glibc/LICENSES',
            'gcc-COPYING.RUNTIME': runtime / 'sdk_snapshot/sysroot/usr/share/xos-glibc/compiler-runtime-licenses/COPYING.RUNTIME',
            'gcc-COPYING': runtime / 'sdk_snapshot/sysroot/usr/share/xos-glibc/compiler-runtime-licenses/COPYING',
            'mbedtls-LICENSE': program / 'notices/LICENSE',
            'tf-psa-LICENSE': program / 'notices/tf-psa-crypto/LICENSE',
            'mbedtls-framework-LICENSE': program / 'notices/framework/LICENSE'}
        licenses = []
        for name, source in license_sources.items():
            path = package_prefix + '/licenses/' + name
            add(path, source)
            licenses.append(path)
        receipt_path = package_prefix + '/build_receipt.json'
        receipt = out / 'build_receipt.json'
        receipt.write_bytes(canonical({'status': 'built_not_run', 'composition': composition,
            'files': files, 'license_election': 'Mbed TLS/TF-PSA: Apache-2.0',
            'sources': {'repository': 'https://github.com/Xiao-John/XylophoneOS',
                        'glibc': gnu['glibc_source_verification']['archive_sha256'],
                        'gcc': gnu['gcc_source_verification']['archive_sha256'],
                        'mbedtls': app['tls']['archive_sha256']},
            'limits': ['private named qualification fixture', 'not a new default release',
                       'ISO boot remains required', 'test trust roots only']}))
        add(receipt_path, receipt)
        manifest = {'format_version': 1, 'id': 'p1_k4_installed_dhcp_tls', 'upstream_version': '1', 'revision': 0,
            'target_profile': profile['id'], 'required_features': ['static_tls', 'file_io', 'stdio'],
            'runtime_dependencies': [], 'files': list(files.values()), 'licenses': licenses,
            'build_receipt': {'path': receipt_path, 'sha256': sha_file(receipt)},
            'source': 'https://github.com/Xiao-John/XylophoneOS; pinned public GNU startup and native TLS fixtures'}
        package = out / 'installed_dhcp_tls.xpk'
        pack_package(root, manifest, package)
        verified = verify_package(package, profile)
        (out / 'package_manifest.json').write_bytes(canonical(verified['manifest']))
        seed = out / 'empty.img'
        create_fat32(seed, 512)
        installed = out / 'installed.img'
        transaction = transact(seed, installed, profile, 'install', package=package, expected_sha256=verified['sha256'])
        report.update(status='installed_candidate_not_run', composition=composition,
            package_sha256=verified['sha256'], package_id=manifest['id'], package_profile=profile['id'],
            profile_sha256=sha_file(out / 'profile.json'), empty_disk_sha256=sha_file(seed),
            installed_disk_sha256=sha_file(installed), transaction=transaction,
            installed=query_image(installed, profile, 'verify-installed'), installed_files=files,
            builder_sha256=sha_file(Path(__file__)))
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        (out / 'installation.json').write_bytes(canonical(report))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'program', 'launcher', 'runtime', 'certificates', 'profile', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--system-source', type=Path, default=repository_root)
    parser.add_argument('--runtime-source-revision', required=True)
    compose(parser.parse_args())
