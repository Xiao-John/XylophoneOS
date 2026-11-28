#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Validate a recorded P1-A proposal using only its recorded inputs.

This is an offline evaluator, never an executor or a live authority service.
No clock, random source, model, network, subprocess or retry supplies inputs.
Success means accepted_proposal, with execution_authority=false in every result.
The three local v1 schemas and validator bytes are hashed into each result.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import sys


root = Path(__file__).resolve().parents[1]
schema_names = ('observation_v1.schema.json', 'proposal_v1.schema.json',
                'observation_replay_v1.schema.json')
max_bytes = 65536
max_depth = 12
max_age_ns = 30_000_000_000
actions = ('inspect', 'diagnose', 'refresh_observation')
scopes = {
    'process': ('self', 'direct_child'),
    'service': ('held_endpoint',),
    'resource': ('self', 'direct_child'),
    'runtime': ('controller',),
    'network': ('service',),
    'trust': ('application',),
}


class invalid_record(ValueError):
    """An input does not satisfy the bounded recorded-input contract."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('ascii')


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise invalid_record('duplicate JSON member')
        value[key] = item
    return value


def _not_integer(_value):
    raise invalid_record('only integer JSON numbers are supported')


def decode(data):
    """Bound bytes/nesting before parsing; reject ambiguous JSON encodings."""
    if not isinstance(data, bytes) or len(data) > max_bytes:
        raise invalid_record('record byte budget exceeded')
    depth, quoted, escaped = 0, False, False
    for byte in data:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (91, 123):
            depth += 1
            if depth > max_depth:
                raise invalid_record('record nesting budget exceeded')
        elif byte in (93, 125):
            depth -= 1
    try:
        return json.loads(data.decode('utf-8'), object_pairs_hook=_pairs,
                          parse_float=_not_integer, parse_constant=_not_integer)
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as error:
        raise invalid_record('invalid bounded JSON') from error


def read_record(path):
    with path.open('rb') as stream:
        return decode(stream.read(max_bytes + 1))


def schemas():
    # Fixed checked-in names only. $ref never causes filesystem or network lookup.
    values, identities = {}, {}
    for name in schema_names:
        data = (root / 'docs/schemas' / name).read_bytes()
        values[name] = json.loads(data)
        identities[name] = sha256(data).hexdigest()
    return values, identities


def _schema_check(value, schema, all_schemas, current):
    """Evaluate the small, closed JSON Schema subset used by the v1 schemas.

    This deliberately has no dynamic/remote reference loader. Unknown schema
    keywords fail closed so future schema changes cannot silently weaken checks.
    """
    supported = {'$schema', '$id', '$defs', '$ref', 'title', 'description', 'type',
                 'const', 'enum', 'properties', 'required', 'additionalProperties',
                 'items', 'minItems', 'maxItems', 'uniqueItems', 'minimum', 'maximum',
                 'minLength', 'maxLength', 'pattern', 'oneOf'}
    if set(schema) - supported:
        raise invalid_record('unsupported local schema keyword')
    if '$ref' in schema:
        ref = schema['$ref']
        if ref.startswith('#/$defs/'):
            target = all_schemas[current]['$defs'][ref[len('#/$defs/'):]]
            _schema_check(value, target, all_schemas, current)
        elif ref in all_schemas:
            _schema_check(value, all_schemas[ref], all_schemas, ref)
        else:
            raise invalid_record('unsupported local schema reference')
        return
    if 'oneOf' in schema:
        count = 0
        for variant in schema['oneOf']:
            try:
                _schema_check(value, variant, all_schemas, current)
            except invalid_record:
                pass
            else:
                count += 1
        if count != 1:
            raise invalid_record('record variant mismatch')
    kind = schema.get('type')
    types = {'object': dict, 'array': list, 'integer': int, 'string': str,
             'boolean': bool}
    if kind is not None and type(value) is not types[kind]:
        raise invalid_record('record type mismatch')
    if 'const' in schema and (type(value) is not type(schema['const']) or value != schema['const']):
        raise invalid_record('record constant mismatch')
    if 'enum' in schema and not any(type(value) is type(item) and value == item for item in schema['enum']):
        raise invalid_record('record enumeration mismatch')
    if kind == 'object':
        properties = schema.get('properties', {})
        if set(schema.get('required', ())) - set(value):
            raise invalid_record('missing record member')
        if schema.get('additionalProperties') is False and set(value) - set(properties):
            raise invalid_record('unknown record member')
        for key in value.keys() & properties.keys():
            _schema_check(value[key], properties[key], all_schemas, current)
    elif kind == 'array':
        if not schema.get('minItems', 0) <= len(value) <= schema.get('maxItems', max_bytes):
            raise invalid_record('record array budget exceeded')
        if schema.get('uniqueItems') and len({canonical(item) for item in value}) != len(value):
            raise invalid_record('duplicate record array member')
        for item in value:
            _schema_check(item, schema.get('items', {}), all_schemas, current)
    elif kind == 'integer':
        if value < schema.get('minimum', value) or value > schema.get('maximum', value):
            raise invalid_record('integer out of range')
    elif kind == 'string':
        if not schema.get('minLength', 0) <= len(value) <= schema.get('maxLength', max_bytes):
            raise invalid_record('record string budget exceeded')
        if 'pattern' in schema and re.fullmatch(schema['pattern'], value) is None:
            raise invalid_record('record string pattern mismatch')


def _semantic_check(record):
    observation = record['observation']
    if observation['valid_until_ns'] <= observation['logical_time_ns']:
        raise invalid_record('empty observation validity interval')
    if observation['valid_until_ns'] - observation['logical_time_ns'] > max_age_ns:
        raise invalid_record('observation validity budget exceeded')
    if observation['status'] != 'ok' and observation['records']:
        raise invalid_record('failed observation discloses records')
    identities = set()
    for item in observation['records']:
        identity = (item['kind'], item['object_id'])
        if identity in identities:
            raise invalid_record('ambiguous object identity')
        identities.add(identity)
        if item['scope'] not in scopes[item['kind']]:
            raise invalid_record('invalid observation scope')
        if item['status'] != 'ok':
            if item['data']:
                raise invalid_record('failed record discloses data')
            continue
        if not item['object_id'] or not item['generation']:
            raise invalid_record('successful record lacks identity')
        data = item['data']
        if item['kind'] in ('process', 'resource') and item['scope'] == 'self':
            if item['object_id'] != observation['source']['pid']:
                raise invalid_record('self scope identity mismatch')
        if item['kind'] == 'process' and item['scope'] == 'direct_child':
            if data['parent_pid'] != observation['source']['pid'] or item['object_id'] == observation['source']['pid']:
                raise invalid_record('direct child identity mismatch')
        if item['kind'] == 'resource':
            if (data['owner_pid'] != item['object_id'] or
                    data['endpoints_used'] > data['endpoint_limit'] or
                    data['names_used'] > data['name_limit']):
                raise invalid_record('invalid owner resource accounting')
            if item['scope'] == 'direct_child' and (data['parent_pid'] != observation['source']['pid'] or
                                                    item['object_id'] == observation['source']['pid']):
                raise invalid_record('direct child resource identity mismatch')
        if item['kind'] == 'network' and data['service_pid'] != item['object_id']:
            raise invalid_record('network identity mismatch')
        if item['kind'] == 'network' and data['mode'] == 'disabled' and data['state'] == 'ready':
            raise invalid_record('disabled network cannot be ready')
        if item['kind'] == 'runtime' and data['controller_pid'] != observation['source']['pid']:
            raise invalid_record('runtime controller identity mismatch')
        if item['kind'] == 'trust' and (data['owner_pid'] != observation['source']['pid'] or
                                       item['object_id'] != item['generation']):
            raise invalid_record('trust selection identity mismatch')
    allowed = [(item['kind'], item['object_id']) for item in record['policy']['allowed_targets']]
    if len(allowed) != len(set(allowed)):
        raise invalid_record('ambiguous policy target')


def evaluate(record):
    """Return a deterministic typed verdict, without granting execution authority."""
    all_schemas, identities = schemas()
    result = {'schema_version': 1, 'validator_version': 1, 'policy_version': 1,
              'execution_authority': False, 'automatic_retry': False,
              'schema_sha256': identities,
              'validator_sha256': sha256(Path(__file__).read_bytes()).hexdigest()}

    def verdict(status, reason):
        return dict(result, status=status, reason=reason)

    try:
        # Direct Python callers receive the same bounded input discipline as CLI.
        encoded = canonical(record)
        record = decode(encoded)
        result['input_sha256'] = sha256(encoded).hexdigest()
        if not isinstance(record, dict):
            raise invalid_record('record is not an object')
        version_objects = ((record, 'schema_version'), (record, 'validator_version'),
                           (record, 'policy_version'))
        for container, field in version_objects:
            if type(container.get(field)) is not int:
                raise invalid_record('version is not an integer')
            if container[field] != 1:
                return verdict('unsupported', field)
        for name in ('observation', 'proposal'):
            container = record.get(name)
            if not isinstance(container, dict) or type(container.get('schema_version')) is not int:
                raise invalid_record('missing nested schema version')
            if container['schema_version'] != 1:
                return verdict('unsupported', name + '_schema_version')
        _schema_check(record, all_schemas[schema_names[2]], all_schemas, schema_names[2])
        _semantic_check(record)
    except (invalid_record, ValueError, TypeError, OverflowError, RecursionError):
        return verdict('invalid', 'record_contract')

    observation, proposal, policy = record['observation'], record['proposal'], record['policy']
    now = record['logical_time_ns']
    if proposal['action'] not in actions:
        return verdict('unsupported', 'proposal_action')
    if not (proposal['caller_pid'] == observation['caller_pid'] == policy['caller_pid']):
        return verdict('unauthorized', 'caller_identity')
    if proposal['action'] not in policy['allowed_actions']:
        return verdict('unauthorized', 'proposal_policy')
    if proposal['source'] != observation['source']:
        return verdict('stale', 'source_incarnation')
    if proposal['observation_id'] != observation['observation_id']:
        return verdict('stale', 'observation_identity')
    if now < observation['logical_time_ns']:
        return verdict('invalid', 'logical_time_before_observation')
    if (now >= observation['valid_until_ns'] or now >= proposal['expires_ns'] or
            now - observation['logical_time_ns'] > policy['max_observation_age_ns']):
        return verdict('deadline', 'recorded_validity')
    if observation['status'] != 'ok':
        return verdict(observation['status'], 'observation_outcome')
    target = proposal['target']
    target_key = (target['kind'], target['object_id'])
    allowed_targets = {(item['kind'], item['object_id']) for item in policy['allowed_targets']}
    if target_key not in allowed_targets:
        return verdict('unauthorized', 'target_policy')
    matches = [item for item in observation['records'] if (item['kind'], item['object_id']) == target_key]
    if not matches:
        # Absence in a bounded or failed observation never proves nonexistence.
        return verdict('unavailable', 'target_not_observed')
    item = matches[0]
    if item['scope'] not in policy['allowed_scopes']:
        return verdict('unauthorized', 'scope_policy')
    if item['status'] != 'ok':
        return verdict(item['status'], 'target_observation_outcome')
    if item['generation'] != target['generation']:
        return verdict('stale', 'target_generation')
    return verdict('accepted_proposal', 'validated_recorded_proposal')


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('record', type=Path)
    args = parser.parse_args()
    try:
        result = evaluate(read_record(args.record))
    except (OSError, invalid_record):
        result = {'schema_version': 1, 'validator_version': 1, 'policy_version': 1,
                  'status': 'invalid', 'reason': 'bounded_json',
                  'execution_authority': False, 'automatic_retry': False}
    sys.stdout.buffer.write(canonical(result) + b'\n')
    return 0 if result['status'] == 'accepted_proposal' else 2 if result['status'] == 'invalid' else 1


if __name__ == '__main__':
    raise SystemExit(main())
