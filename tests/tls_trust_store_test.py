#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise the real PEM compiler and exclusive trust snapshot publication."""
import argparse
import base64
from hashlib import sha256
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from package_tls_trust_store import (MAX_SOURCE, compile_snapshot, publish_snapshot)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'scope': 'real_host_openssl_and_snapshot_compiler',
              'checks': [], 'source_sha256': {
                  str(path.relative_to(ROOT)): sha256(path.read_bytes()).hexdigest()
                  for path in (Path(__file__), ROOT / 'scripts/package_tls_trust_store.py')}}
    try:
        report['openssl'] = subprocess.check_output(['openssl', 'version'], text=True).strip()
        with tempfile.TemporaryDirectory(prefix='xos-trust-compiler-') as temporary:
            directory = Path(temporary)

            def certificate(name, ca, usage):
                subprocess.run(['openssl', 'req', '-x509', '-newkey', 'ec', '-pkeyopt',
                                'ec_paramgen_curve:P-256', '-noenc', '-sha256', '-days', '1',
                                '-subj', '/CN=XOS synthetic ' + name,
                                '-addext', 'basicConstraints=critical,CA:' + ca,
                                '-addext', 'keyUsage=critical,' + usage,
                                '-keyout', str(directory / (name + '.key')),
                                '-out', str(directory / (name + '.pem'))],
                               check=True, capture_output=True)
                return (directory / (name + '.pem')).read_bytes()

            first = certificate('root-one', 'TRUE', 'keyCertSign,cRLSign')
            second = certificate('root-two', 'TRUE', 'keyCertSign')
            leaf = certificate('leaf', 'FALSE', 'digitalSignature')
            wrong_usage = certificate('wrong-usage', 'TRUE', 'digitalSignature')

            def check(name, condition):
                if not condition:
                    raise AssertionError(name)
                report['checks'].append({'name': name, 'status': 'passed'})

            def rejected(name, operation):
                try:
                    operation()
                except (ValueError, OSError):
                    report['checks'].append({'name': name, 'status': 'passed'})
                else:
                    raise AssertionError(name + ': unexpectedly accepted')

            data, anchors = compile_snapshot(first + second, 7)
            reordered, reordered_anchors = compile_snapshot(second + first, 7)
            check('deterministic sorted CA closure', data == reordered and anchors == reordered_anchors)
            check('exact format identity and count', struct.unpack('<8sIIQQ', data[:32]) ==
                  (b'XOSTRUST', 1, 2, 7, 0))
            changed, _ = compile_snapshot(first + second, 8)
            check('generation changes snapshot identity', sha256(data).digest() != sha256(changed).digest())
            rejected('empty source', lambda: compile_snapshot(b'', 1))
            rejected('oversized source', lambda: compile_snapshot(b'x' * (MAX_SOURCE + 1), 1))
            rejected('zero generation', lambda: compile_snapshot(first, 0))
            rejected('overflow generation', lambda: compile_snapshot(first, 2**64))
            rejected('boolean generation', lambda: compile_snapshot(first, True))
            rejected('duplicate anchor', lambda: compile_snapshot(first + first, 1))
            rejected('leaf cannot grant trust', lambda: compile_snapshot(leaf, 1))
            rejected('CA without certificate signing usage', lambda: compile_snapshot(wrong_usage, 1))
            rejected('malformed certificate PEM', lambda: compile_snapshot(
                b'-----BEGIN CERTIFICATE-----\n!!!\n-----END CERTIFICATE-----\n', 1))
            rejected('unrecognized private-key block', lambda: compile_snapshot(
                first + b'-----BEGIN PRIVATE KEY-----\nAAAA\n-----END PRIVATE KEY-----\n', 1))
            rejected('certificate-count budget', lambda: compile_snapshot(first * 257, 1))
            der = subprocess.check_output(['openssl', 'x509', '-inform', 'PEM', '-outform', 'DER'], input=first)
            extra = b'-----BEGIN CERTIFICATE-----\n' + base64.b64encode(der + b'garbage') + b'\n-----END CERTIFICATE-----\n'
            rejected('DER trailing bytes', lambda: compile_snapshot(extra, 1))
            malformed = b'-----BEGIN CERTIFICATE-----\n' + base64.b64encode(b'not a certificate') + b'\n-----END CERTIFICATE-----\n'
            rejected('malformed DER', lambda: compile_snapshot(malformed, 1))

            destination = directory / 'published.bin'
            publish_snapshot(destination, data)
            check('complete publication', destination.read_bytes() == data)
            rejected('existing generation cannot be overwritten', lambda: publish_snapshot(destination, changed))
            check('failed replacement preserves old bytes', destination.read_bytes() == data)
            dangling = directory / 'dangling.bin'
            dangling.symlink_to(directory / 'missing')
            rejected('symlink destination cannot be replaced', lambda: publish_snapshot(dangling, data))
            check('publication temporary files cleaned', not list(directory.glob('.xos_trust_*')))

            input_file = directory / 'input.pem'
            input_file.write_bytes(first)
            output_file = directory / 'cli.bin'
            command = [sys.executable, str(ROOT / 'scripts/package_tls_trust_store.py'),
                       '--pem', str(input_file), '--source-sha256', '0' * 64,
                       '--source-url', 'https://example.invalid/synthetic-ca.pem',
                       '--generation', '1', '--output', str(output_file)]
            rejected_pin = subprocess.run(command, capture_output=True, text=True)
            check('CLI rejects source pin before publishing', rejected_pin.returncode != 0 and not output_file.exists())
            command[command.index('--source-sha256') + 1] = sha256(first).hexdigest()
            passed = subprocess.run(command, check=True, capture_output=True, text=True)
            receipt = json.loads(passed.stdout)
            check('CLI receipt binds real output', receipt['sha256'] == sha256(output_file.read_bytes()).hexdigest()
                  and receipt['source_sha256'] == sha256(first).hexdigest() and len(receipt['anchor_sha256']) == 1)
            output_file.unlink()
            command[command.index('--source-url') + 1] = 'https://name:secret@example.invalid/ca.pem'
            invalid_url = subprocess.run(command, capture_output=True, text=True)
            check('provenance URL cannot contain credentials', invalid_url.returncode != 0 and not output_file.exists())
        report['status'] = 'passed'
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({'status': report['status'], 'checks': len(report['checks'])}))


if __name__ == '__main__':
    main()
