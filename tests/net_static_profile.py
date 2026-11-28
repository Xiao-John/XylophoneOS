#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reject ambiguous resolver authority while retaining old profile schemas."""
import copy
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from lwip_service_build import load_static_profile

base = {'revision': 3, 'pci_instance': 41, 'resolvers': ['10.0.2.2', '10.0.2.3'], 'egress': []}
changes = [('revision', True), ('revision', 4), ('pci_instance', False), ('pci_instance', 0),
           ('resolvers', []), ('resolvers', '10.0.2.2'), ('resolvers', ['10.0.2.2'] * 2),
           ('resolvers', ['10.0.2.2', '10.0.2.3', '10.0.2.4']), ('resolvers', [False]),
           ('resolvers', ['127.0.0.1']), ('resolvers', ['224.0.0.1']), ('resolvers', ['10.0.2.0']),
           ('resolvers', ['10.0.2.15']), ('resolvers', ['10.0.2.255']), ('resolvers', ['10.0.3.2'])]
with tempfile.TemporaryDirectory(prefix='xos_static_profile_') as temporary:
    path = Path(temporary) / 'profile.json'
    for profile in (base, dict(base, resolvers=['10.0.2.2']),
                    {'revision': 1, 'pci_instance': 41, 'resolver': '10.0.2.2'},
                    {'revision': 2, 'pci_instance': 41, 'resolver': '10.0.2.2', 'egress': []}):
        path.write_text(json.dumps(profile))
        parsed = load_static_profile(path)
        assert {k: v for k, v in parsed.items() if k != 'source_sha256'} == profile
    negatives = [dict(base, **{field: value}) for field, value in changes]
    negatives += [dict(base, resolver='10.0.2.2'), {k: v for k, v in base.items() if k != 'egress'}]
    for candidate in negatives:
        path.write_text(json.dumps(candidate))
        try:
            load_static_profile(path)
        except ValueError:
            continue
        raise AssertionError('accepted invalid profile: ' + repr(candidate))
print('STATIC_PROFILE_PASS compatibility=4 negatives=' + str(len(negatives)))
