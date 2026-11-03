#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Review exact staged guest fixtures without suppressing private-path findings."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root_path = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root_path / 'tests'))
import check_public_evidence_paths as scanner
from verify_evidence_index import git_reader, no_duplicates, safe_path
from verify_evidence_migration import conversion_dir, expected_export, run as verify_migration

guest_prefixes = ('/tests/', '/out/', '/src/', '/missing/', '/work/')
reviewable_categories = {'absolute_command', 'private_temp'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def inspect_guest_data(current, original):
    """Prove remaining command paths are unchanged guest/test data."""
    observed = collections.Counter()

    def walk(value, source, path=(), in_command=False):
        require(type(value) is type(source), 'guest fixture type changed')
        if isinstance(value, dict):
            source_keys = {}
            for key in source:
                converted = expected_export(key.encode()).decode()
                require(converted not in source_keys, 'guest fixture key collision')
                source_keys[converted] = key
            require(value.keys() == source_keys.keys(), 'guest fixture keys changed')
            for key, item in value.items():
                require(not scanner.compiled['private_temp'].search(key.encode()), 'temporary path in JSON key')
                walk(item, source[source_keys[key]], path + (key,), in_command or key in scanner.command_keys)
        elif isinstance(value, list):
            require(len(value) == len(source), 'guest fixture list changed')
            for i, item in enumerate(value):
                walk(item, source[i], path + (i,), in_command)
        elif isinstance(value, str):
            labels = tuple(x for x in path if isinstance(x, str))
            if scanner.compiled['private_temp'].search(value.encode()):
                require(labels and labels[0] == 'host_reference' and labels[-1] in ('input', 'stderr'),
                        'temporary path is not a reviewed test input/output')
                require(value == source, 'guest temporary-path data changed')
                observed['private_temp'] += 1
            if in_command:
                text = scanner.url_pattern.sub('${URL}', scanner.template_path.sub('${XOS_TEMPLATE}', json.dumps(value, ensure_ascii=False)))
                matches = [m.group() for m in scanner.absolute_path.finditer(text)
                           if not m.group().startswith(scanner.system_paths)]
                if matches:
                    require(not any(label in ('qemu_command', 'qemu_commands', 'threaded_probe', 'host_reference') for label in labels),
                            'untemplated path in a host command')
                    require(all(match.startswith(guest_prefixes) for match in matches), 'unreviewed absolute command path')
                    require(value == source, 'guest command data changed')
                    observed['absolute_command'] += len(matches)

    walk(current, original)
    return observed


def review(root, base, revision, identities=()):
    root = root.resolve()
    result = scanner.scan_repository(root, source='commit', base=base, commit=revision, identities=identities)
    require(result['files_selected'] == result['files_scanned'], 'scan coverage incomplete')
    migration = verify_migration(root, revision)
    reader = git_reader(root, revision)
    sources = {}
    try:
        review_path = safe_path(conversion_dir + '/reviewed_guest_findings.json')
        plan = json.loads(reader.read(review_path), object_pairs_hook=no_duplicates)
        require(plan.get('version') == 1 and isinstance(plan.get('records'), list), 'invalid guest review plan')
        plans = {}
        for item in plan['records']:
            path = str(safe_path(item['path']))
            require(path not in plans and item.get('classification') == 'GUEST_TEST_DATA', 'invalid guest review entry')
            require(set(item.get('findings', {})) <= reviewable_categories, 'non-guest category cannot be reviewed away')
            plans[path] = item
        actual = collections.defaultdict(collections.Counter)
        for finding in result['findings']:
            require(finding['status'] != 'UNVERIFIED' and finding['category'] in reviewable_categories and
                    '!' not in finding['location'], 'private, unverified or archive finding cannot be reviewed away')
            actual[finding['location']][finding['category']] += 1
        semantic = collections.Counter()
        for path, counts in actual.items():
            require(path in plans and dict(counts) == plans[path]['findings'], 'unreviewed or changed finding count')
            ledger_name = plans[path]['ledger']
            require('/' not in ledger_name and ledger_name.endswith('_lineage.json'), 'invalid conversion ledger name')
            ledger = json.loads(reader.read(safe_path(conversion_dir + '/' + ledger_name)), object_pairs_hook=no_duplicates)
            changes = [x for x in ledger['changes'] if x['path'] == path]
            require(len(changes) == 1, 'guest fixture not bound to a conversion record')
            current_bytes = reader.read(safe_path(path))
            require(hashlib.sha256(current_bytes).hexdigest() == changes[0]['export_sha256'], 'guest export hash mismatch')
            commit = ledger['source_commit']
            if commit not in sources:
                ancestor = subprocess.run(['git', '-C', str(root), 'merge-base', '--is-ancestor', commit, base],
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                require(ancestor.returncode == 0, 'guest source is not an ancestor of the base')
                sources[commit] = git_reader(root, commit)
            original_bytes = sources[commit].read(safe_path(path))
            require(hashlib.sha256(original_bytes).hexdigest() == changes[0]['original_sha256'], 'guest source hash mismatch')
            current = json.loads(current_bytes, object_pairs_hook=no_duplicates)
            original = json.loads(original_bytes, object_pairs_hook=no_duplicates)
            observed = inspect_guest_data(current, original)
            require(all(observed[category] for category in counts), 'reviewed category has no validated guest data')
            semantic.update(observed)
        return {'status': 'PASS_WITH_REVIEWED_GUEST_FIXTURES',
                'scope': 'no personal-path or unverified finding is suppressible; guest data remains source-identical',
                'files_scanned': result['files_scanned'], 'reviewed_files': len(actual),
                'reviewed_findings': sum(sum(x.values()) for x in actual.values()),
                'validated_guest_occurrences': dict(semantic), 'migration': migration}
    finally:
        for source in sources.values():
            source.close()
        reader.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=root_path)
    parser.add_argument('--base', required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--deny-identity', action='append', default=[])
    args = parser.parse_args()
    try:
        result = review(args.root, args.base, args.commit, args.deny_identity)
    except (OSError, EOFError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(json.dumps({'status': 'FAIL', 'error_type': type(error).__name__}, indent=2))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
