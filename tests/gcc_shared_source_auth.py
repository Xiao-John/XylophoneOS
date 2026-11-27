# SPDX-License-Identifier: Apache-2.0
"""Real locked GCC signature and exact input refusals; no target runtime claim."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from verify_gcc_shared_source import check_status, extract_verified_source, read_archive, read_lock, verify_source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('archive', 'signature', 'keyring', 'output'):
        parser.add_argument('--' + flag, type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    lock, _ = read_lock()
    data = read_archive(args.archive, lock['archive_bytes'])
    verified = verify_source(args.archive, args.signature, args.keyring, args.output / 'verified',
                              archive_data=data)
    status = (args.output / 'verified/gpgv.status').read_text()
    cases = {'real_gpgv_signature_and_current_keyring': 'passed'}
    for name, bad in [('wrong_signer', status.replace(lock['signing_fingerprint'], '0' * 40)),
                       ('wrong_primary', status.replace(lock['primary_fingerprint'], '1' * 40)),
                       ('duplicate_signature', status + status),
                       *((name.lower(), status + '[GNUPG:] ' + name + '\n')
                         for name in ('BADSIG', 'ERRSIG', 'EXPKEYSIG', 'REVKEYSIG', 'KEYEXPIRED',
                                      'SIGEXPIRED', 'KEYREVOKED', 'FAILURE', 'ERROR'))]:
        try:
            check_status(0, bad, lock)
        except ValueError:
            cases[name] = 'rejected_status_fixture'
        else:
            raise AssertionError(name + ' accepted')
    try:
        check_status(1, status, lock)
    except ValueError:
        cases['nonzero_verifier_exit'] = 'rejected_status_fixture'
    else:
        raise AssertionError('failed verifier accepted')
    for name, original in [('signature', args.signature), ('keyring', args.keyring)]:
        path = args.output / ('altered_' + name)
        body = original.read_bytes()
        path.write_bytes(bytes([body[0] ^ 1]) + body[1:])
        try:
            verify_source(args.archive, path if name == 'signature' else args.signature,
                          path if name == 'keyring' else args.keyring,
                          args.output / ('reject_' + name), archive_data=data)
        except ValueError as error:
            if name + ' SHA-256 differs' not in str(error):
                raise
            cases['altered_' + name] = 'rejected_real_file'
        else:
            raise AssertionError('changed source input accepted: ' + name)
    changed = bytes([data[0] ^ 1]) + data[1:]
    try:
        extract_verified_source(changed, verified, args.output / 'not_extracted')
    except ValueError:
        cases['changed_extraction_snapshot'] = 'rejected_before_extraction'
    else:
        raise AssertionError('changed extraction bytes accepted')
    if (args.output / 'not_extracted').exists():
        raise AssertionError('failed extraction created an output')
    report = {'status': 'passed', 'scope': 'source signature and input binding, not target runtime',
              'cases': cases, 'verification_report_sha256': hashlib.sha256(
                  (args.output / 'verified/report.json').read_bytes()).hexdigest()}
    (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS', len(cases), 'GCC shared source authentication checks')


if __name__ == '__main__':
    main()
