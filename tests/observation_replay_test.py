#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise the offline P1-A boundary with recorded pairs and hostile inputs."""
import argparse
import copy
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'scripts'))
import observation_replay as replay

fixtures = root / 'tests/fixtures/observation'


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.output:
        args.output.mkdir(parents=True, exist_ok=False)
    sources = [Path(__file__), root / 'scripts/observation_replay.py']
    sources += sorted((root / 'docs/schemas').glob('*_v1.schema.json'))
    sources += sorted(fixtures.glob('*.json'))
    identities = lambda: {str(path.relative_to(root)): sha256(path.read_bytes()).hexdigest() for path in sources}
    report = {'status': 'failed', 'scope': 'offline evaluator and synthetic recorded pairs',
              'guest': 'not_run', 'source_sha256': identities(), 'checks': []}

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        report['checks'].append({'name': name, 'status': 'passed'})

    def outcome(name, record, status, reason=None):
        value = replay.evaluate(record)
        check(name, value['status'] == status and (reason is None or value['reason'] == reason))
        check(name + ' cannot execute or retry', value['execution_authority'] is False and
              value['automatic_retry'] is False)
        return value

    def mutate(base, path, replacement):
        value = copy.deepcopy(base)
        owner = value
        for key in path[:-1]:
            owner = owner[key]
        owner[path[-1]] = replacement
        return value

    try:
        expected = json.loads((fixtures / 'expected.json').read_text())
        for item in expected['cases']:
            outcome('fixture ' + item['file'], replay.read_record(fixtures / item['file']),
                    item['status'], item['reason'])
        base = replay.read_record(fixtures / 'self_inspect.json')
        accepted = replay.evaluate(base)
        for item in base['observation']['records']:
            for action in replay.actions:
                value = copy.deepcopy(base)
                value['proposal']['target'] = {key: item[key] for key in ('kind', 'object_id', 'generation')}
                value['proposal']['action'] = action
                outcome(item['kind'] + ' ' + action, value, 'accepted_proposal')

        for state in ('invalid', 'unauthorized', 'stale', 'revoked', 'deadline', 'quota', 'unavailable', 'unsupported'):
            value = copy.deepcopy(base)
            value['observation']['status'] = state
            value['observation']['records'] = []
            outcome('envelope ' + state, value, state, 'observation_outcome')
            value = copy.deepcopy(base)
            value['observation']['records'][0].update(status=state, data={})
            outcome('target ' + state, value, state, 'target_observation_outcome')

        for field in ('schema_version', 'validator_version', 'policy_version'):
            outcome('future ' + field, mutate(base, (field,), 2), 'unsupported', field)
        for key in ('observation', 'proposal'):
            outcome('future ' + key, mutate(base, (key, 'schema_version'), 2), 'unsupported')
        outcome('source process replaced', mutate(base, ('proposal', 'source', 'pid'), 61), 'stale', 'source_incarnation')
        outcome('observation replaced', mutate(base, ('proposal', 'observation_id'), 11), 'stale', 'observation_identity')
        outcome('target generation replaced', mutate(base, ('proposal', 'target', 'generation'), 2), 'stale', 'target_generation')
        outcome('principal replaced', mutate(base, ('proposal', 'caller_pid'), 42), 'unauthorized', 'caller_identity')
        outcome('read scope denied', mutate(base, ('policy', 'allowed_scopes'), ['service']), 'unauthorized', 'scope_policy')
        outcome('proposal policy denies', mutate(base, ('policy', 'allowed_actions'), []), 'unauthorized', 'proposal_policy')
        outcome('record too old', mutate(base, ('policy', 'max_observation_age_ns'), 99), 'deadline')
        outcome('logical time rolled backwards', mutate(base, ('logical_time_ns',), 999), 'invalid')
        outcome('proposal expired at exact deadline', mutate(base, ('proposal', 'expires_ns'), 1100), 'deadline')
        outcome('unobserved target remains unknown', mutate(base, ('observation', 'records'), []), 'unavailable', 'target_not_observed')
        value = copy.deepcopy(base)
        value['observation']['records'][0].update(status='unavailable', object_id=0, generation=0, data={})
        outcome('unknown identity cannot certify absence', value, 'unavailable', 'target_not_observed')

        invalid = [
            ('boolean ID', ('proposal', 'target', 'object_id'), True),
            ('zero successful generation', ('observation', 'records', 0, 'generation'), 0),
            ('out of range integer', ('proposal', 'proposal_id'), 2**64),
            ('negative integer', ('logical_time_ns',), -1),
            ('float integer', ('logical_time_ns',), 1100.0),
            ('wrong self principal', ('observation', 'records', 0, 'object_id'), 99),
            ('invalid cross-domain scope', ('observation', 'records', 4, 'scope'), 'self'),
            ('resource over quota', ('observation', 'records', 2, 'data', 'endpoints_used'), 17),
            ('resource endpoint limit cannot be invented', ('observation', 'records', 2, 'data', 'endpoint_limit'), 16),
            ('resource name limit cannot be invented', ('observation', 'records', 2, 'data', 'name_limit'), 4),
            ('process thread limit', ('observation', 'records', 0, 'data', 'threads'), 65),
            ('service metadata revision cannot imply target ABI', ('observation', 'records', 1, 'data', 'interface_version'), 2),
            ('network owner mismatch', ('observation', 'records', 4, 'data', 'service_pid'), 99),
            ('disabled network cannot be ready', ('observation', 'records', 4, 'data', 'mode'), 'disabled'),
            ('runtime controller mismatch', ('observation', 'records', 3, 'data', 'controller_pid'), 99),
            ('trust owner mismatch', ('observation', 'records', 5, 'data', 'owner_pid'), 99),
            ('configured pin is not an active trust snapshot', ('observation', 'records', 5, 'data', 'selection'), 'configured_pin'),
            ('unknown trust selection is rejected', ('observation', 'records', 5, 'data', 'selection'), 'loaded_store'),
            ('failed envelope cannot leak data', ('observation', 'status'), 'unauthorized'),
            ('failed item cannot leak data', ('observation', 'records', 0, 'status'), 'unauthorized'),
            ('empty validity', ('observation', 'valid_until_ns'), 1000),
            ('unbounded validity', ('observation', 'valid_until_ns'), replay.max_age_ns + 1001),
            ('unexpected executor request', ('proposal', 'command'), 'execute'),
            ('overlong proposal action', ('proposal', 'action'), 'x' * 33),
            ('duplicate permitted actions', ('policy', 'allowed_actions'), ['inspect', 'inspect']),
            ('malformed digest', ('observation', 'records', 3, 'data', 'digest'), 'z' * 64),
            ('zero runtime digest', ('observation', 'records', 3, 'data', 'digest'), '0' * 64),
            ('zero trust digest', ('observation', 'records', 5, 'data', 'digest'), '0' * 64),
        ]
        for name, path, replacement in invalid:
            outcome(name, mutate(base, path, replacement), 'invalid')
        value = copy.deepcopy(base)
        value['observation']['records'].append(copy.deepcopy(value['observation']['records'][0]))
        outcome('ambiguous target observations', value, 'invalid')
        value = copy.deepcopy(base)
        value['observation']['records'] = value['observation']['records'] * 6
        outcome('observation item budget', value, 'invalid')
        value = copy.deepcopy(base)
        value['observation']['records'][0]['scope'] = 'direct_child'
        value['observation']['records'][0]['object_id'] = 43
        value['observation']['records'][0]['data']['parent_pid'] = 41
        value['proposal']['target']['object_id'] = 43
        value['policy']['allowed_targets'][0]['object_id'] = 43
        outcome('explicit direct child', value, 'accepted_proposal')
        value['observation']['records'][0]['data']['parent_pid'] = 99
        outcome('direct child cannot rename parent', value, 'invalid')
        value = copy.deepcopy(base)
        value['observation']['records'][2].update(scope='direct_child', object_id=43)
        value['observation']['records'][2]['data'].update(owner_pid=43, parent_pid=41)
        value['proposal']['target'] = {'kind': 'resource', 'object_id': 43, 'generation': 3}
        value['policy']['allowed_targets'][2]['object_id'] = 43
        outcome('explicit direct child resource', value, 'accepted_proposal')
        value['observation']['records'][2]['data']['parent_pid'] = 99
        outcome('direct child resource cannot rename parent', value, 'invalid')

        malformed = {
            'duplicate key': b'{"schema_version":1,"schema_version":1}',
            'nested duplicate key': b'{"a":{"pid":1,"pid":2}}',
            'nonfinite number': b'{"value":NaN}',
            'infinity': b'{"value":Infinity}',
            'exponent number': b'{"value":1e3}',
            'bad UTF-8': b'"\xff"',
            'nesting budget': b'[' * 13 + b'0' + b']' * 13,
            'byte budget': b' ' * (replay.max_bytes + 1),
            'trailing object': b'{}{}',
        }
        for name, raw in malformed.items():
            try:
                replay.decode(raw)
            except replay.invalid_record:
                check(name, True)
            else:
                raise AssertionError(name)

        with tempfile.TemporaryDirectory(prefix='xos-observation-replay-') as directory:
            temporary = Path(directory)
            first, second = temporary / 'first.json', temporary / 'second.json'
            first.write_bytes(replay.canonical(base))
            second.write_text(json.dumps(base, indent=7, sort_keys=False) + '\n')
            command = [sys.executable, '-I', str(root / 'scripts/observation_replay.py')]
            a = subprocess.run(command + [str(first)], cwd=temporary, capture_output=True, check=True,
                               env=dict(os.environ, TZ='UTC', PYTHONHASHSEED='1'))
            b = subprocess.run(command + [str(second)], cwd=root, capture_output=True, check=True,
                               env=dict(os.environ, TZ='Asia/Shanghai', PYTHONHASHSEED='42'))
            check('offline replay stable across processes cwd timezone and JSON formatting', a.stdout == b.stdout)
            check('CLI and direct validation agree', json.loads(a.stdout) == accepted)
            second.write_bytes(malformed['duplicate key'])
            bad = subprocess.run(command + [str(second)], capture_output=True)
            check('CLI invalid encoding is typed with exit 2', bad.returncode == 2 and
                  json.loads(bad.stdout)['status'] == 'invalid')
            denied = subprocess.run(command + [str(fixtures / 'unauthorized.json')], capture_output=True)
            check('CLI policy denial is typed with exit 1', denied.returncode == 1 and
                  json.loads(denied.stdout)['status'] == 'unauthorized')
        check('validation binds exact inputs', accepted['input_sha256'] == sha256(replay.canonical(base)).hexdigest())
        check('validation binds exact implementation', accepted['validator_sha256'] == sha256((root / 'scripts/observation_replay.py').read_bytes()).hexdigest())
        check('validation binds all three schemas', accepted['schema_sha256'] == replay.schemas()[1])
        check('test inputs remained unchanged', identities() == report['source_sha256'])
        report['status'] = 'passed'
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        if args.output:
            (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({'status': report['status'], 'checks': len(report['checks'])}))


if __name__ == '__main__':
    main()
