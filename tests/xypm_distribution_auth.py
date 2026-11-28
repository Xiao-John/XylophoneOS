#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run real EVP signature and production metadata/freshness rejection cases."""
import argparse
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from xypm_format import canonical, sha_file
from xypm_release import DOMAIN, ED25519_SPKI


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--openssl-prefix', type=Path,
                        help='explicit host OpenSSL development snapshot (include/ and lib/libcrypto.so.3)')
    args = parser.parse_args()
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    compiler = shutil.which('g++')
    if not compiler:
        raise RuntimeError('host g++ is required in the SDK development environment')
    sources = [ROOT / 'tests/fixtures/xypm_distribution_auth.cpp',
               ROOT / 'src/user/programs/xypm_repository_auth.cpp']
    inputs = {str(p): sha_file(p) for p in [Path(__file__), *sources,
        ROOT / 'src/user/programs/xypm_repository_auth.hpp', ROOT / 'src/user/programs/xypm_repository.hpp',
        ROOT / 'src/user/programs/xypm_native.hpp', ROOT / 'src/user/include/xos/text.hpp',
        ROOT / 'src/user/include/xos/unicode_width_data.hpp', ROOT / 'src/shared/include/xos/abi_types.hpp']}
    binary = output / 'auth_probe'
    command = [compiler, '-std=c++20', '-O1' if args.sanitize else '-O2', '-g',
               '-Wall', '-Wextra', '-Werror', '-Wno-misleading-indentation', '-I', str(ROOT / 'src/user/programs'),
               '-I', str(ROOT / 'src/user/include'), '-I', str(ROOT / 'src/shared/include')]
    if args.sanitize:
        command += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    crypto = ['-lcrypto']
    if args.openssl_prefix:
        prefix = args.openssl_prefix.resolve(strict=True)
        library = prefix / 'lib/libcrypto.so.3'
        for path in sorted(prefix.rglob('*')):
            if path.is_file():
                inputs[str(path)] = sha_file(path)
        command += ['-I', str(prefix / 'include')]
        crypto = [str(library), '-Wl,-rpath,' + str(library.parent)]
    command += [*map(str, sources), *crypto, '-o', str(binary)]
    report = {'status': 'failed', 'scope': 'real host EVP and production bounded parser/freshness; no guest claim',
              'sanitized': args.sanitize, 'inputs': inputs, 'compile_command': command, 'cases': {}}
    try:
        compiled = subprocess.run(command, text=True, capture_output=True)
        (output / 'compile.log').write_text(compiled.stdout + compiled.stderr)
        compiled.check_returncode()
        report['compiler_version'] = subprocess.check_output([compiler, '--version'], text=True).splitlines()[0]
        report['compiler_sha256'] = sha_file(compiler)
        report['signer_openssl_version'] = subprocess.check_output(['openssl', 'version'], text=True).strip()
        report['verifier_openssl_version'] = subprocess.check_output([binary, '--openssl-version'], text=True).strip()
        report['binary_sha256'] = sha_file(binary)
        keys = []
        for index in range(2):
            private = output / ('test_only_' + str(index) + '.pem')
            subprocess.run(['openssl', 'genpkey', '-algorithm', 'ED25519', '-out', str(private)],
                           check=True, capture_output=True)
            private.chmod(0o600)
            public = subprocess.check_output(['openssl', 'pkey', '-in', str(private), '-pubout', '-outform', 'DER'])
            if not public.startswith(ED25519_SPKI) or len(public) != len(ED25519_SPKI) + 32:
                raise RuntimeError('unexpected test public key')
            keys.append((private, public[len(ED25519_SPKI):].hex()))
        original = {'format_version': 1, 'repository_id': 'xos.test.distribution.only',
                    'target_profile': 'xos-x86_64-glibc-p1-20261128-v1', 'key_epoch': 1,
                    'sequence': 1, 'issued_at': 1000, 'expires_at': 2000,
                    'index_sha256': '1' * 64, 'lock_sha256': '2' * 64,
                    'generation_id': 1101, 'generation_sha256': '3' * 64}
        original_sha = hashlib.sha256(canonical(original)).hexdigest()

        def case(name, expected=None, changes=None, *, raw=None, now=1500, previous=(0, 0, 0, ''),
                 epoch=1, floor=1, validity=604800, signer=0, public=None, mutate=None, domain=DOMAIN):
            directory = output / name
            directory.mkdir()
            metadata = copy.deepcopy(original)
            metadata.update(changes or {})
            body = raw if raw is not None else canonical(metadata)
            message = directory / 'message'
            message.write_bytes(domain + body)
            signature = directory / 'release.sig'
            subprocess.run(['openssl', 'pkeyutl', '-sign', '-rawin', '-inkey', str(keys[signer][0]),
                            '-in', str(message), '-out', str(signature)], check=True, capture_output=True)
            if mutate:
                body, signed = mutate(body, signature.read_bytes())
                signature.write_bytes(signed)
            release = directory / 'release.json'
            release.write_bytes(body)
            argv = [str(binary), public if public is not None else keys[0][1], str(release), str(signature),
                    str(now), *map(str, previous), str(epoch), str(floor), str(validity)]
            result = subprocess.run(argv, text=True, capture_output=True, env=os.environ.copy())
            (directory / 'stdout.log').write_text(result.stdout)
            (directory / 'stderr.log').write_text(result.stderr)
            good = result.returncode == (0 if expected is None else 3) and (
                'accepted sequence=' in result.stdout if expected is None else expected in result.stderr)
            report['cases'][name] = {'status': 'passed' if good else 'failed', 'exit_code': result.returncode,
                'expected_error': expected, 'stdout': result.stdout, 'stderr': result.stderr,
                'metadata_sha256': sha_file(release), 'signature_sha256': sha_file(signature),
                'vector': {'public_key_ed25519': argv[1], 'metadata_base64': base64.b64encode(body).decode('ascii'),
                           'signature_hex': signature.read_bytes().hex(), 'trusted_unix_seconds': now,
                           'previous_checkpoint': list(previous), 'bootstrap_epoch': epoch,
                           'minimum_sequence': floor, 'maximum_validity_seconds': validity}}
            if not good:
                raise RuntimeError('case failed: ' + name + '\n' + result.stdout + result.stderr)

        same = (1, 1, 1400, original_sha)
        case('valid_initial')
        case('identical_verification', previous=same)
        case('next_sequence', changes={'sequence': 2}, previous=same)
        case('altered_bytes', 'signature rejected', mutate=lambda b, s: (b + b' ', s))
        case('other_signer', 'signature rejected', signer=1)
        case('changed_signature', 'signature rejected', mutate=lambda b, s: (b, bytes([s[0] ^ 1]) + s[1:]))
        case('empty_metadata', 'invalid authenticated metadata size', mutate=lambda b, s: (b'', s))
        case('oversized_metadata', 'invalid authenticated metadata size', raw=b' ' * 4097)
        case('expiry_boundary', 'expired or not yet valid', now=2000)
        case('not_yet_valid', 'expired or not yet valid', now=999)
        case('no_trusted_clock', 'trusted repository time is unavailable', now=0)
        case('clock_rollback', 'clock moved backwards', previous=(1, 1, 1600, original_sha))
        case('sequence_rollback', 'metadata rollback rejected', previous=(1, 2, 1400, original_sha))
        case('equivocation', 'sequence equivocation rejected', changes={'generation_id': 1102}, previous=same)
        case('epoch_rollback', 'key epoch rollback rejected', changes={'key_epoch': 2}, epoch=2,
             previous=(3, 1, 1400, original_sha))
        case('unbootstrapped_epoch', 'key epoch is not bootstrapped', changes={'key_epoch': 2})
        case('wrong_repository', 'repository identity mismatch', changes={'repository_id': 'xos.test.untrusted'})
        case('wrong_profile', 'release profile mismatch', changes={'target_profile': 'xos.test.other'})
        case('long_validity', 'validity interval rejected', changes={'expires_at': 1000000})
        case('reversed_validity', 'validity interval rejected', changes={'expires_at': 999})
        case('zero_generation', 'validity interval rejected', changes={'generation_id': 0})
        case('invalid_digest', 'invalid authenticated repository digest', changes={'index_sha256': 'z' * 64})
        case('downloaded_key', 'unknown JSON field', changes={'public_key_ed25519': keys[1][1]})
        duplicate = canonical(original).replace(b'"sequence": 1', b'"sequence": 1, "sequence": 1')
        case('duplicate_field', 'duplicate JSON', raw=duplicate)
        case('fractional_sequence', 'integer', raw=canonical(original).replace(b'"sequence": 1', b'"sequence": 1.5'))
        case('boolean_sequence', 'invalid release sequence', changes={'sequence': True})
        case('unconfigured_key', 'bootstrap trust is not configured', public='0' * 64)
        case('bootstrap_floor', 'predates bootstrap floor', floor=2)
        case('wrong_signature_domain', 'signature rejected', domain=b'')
        case('independent_epoch_rotation', changes={'key_epoch': 2, 'sequence': 2}, epoch=2, previous=same)
        for name, expected in inputs.items():
            if sha_file(name) != expected:
                raise RuntimeError('input changed during test: ' + name)
        report['status'] = 'passed'
        print('PASS authenticated distribution host:', len(report['cases']), 'cases')
    finally:
        (output / 'report.json').write_bytes(canonical(report))


if __name__ == '__main__':
    main()
