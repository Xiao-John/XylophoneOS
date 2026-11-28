#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Installation parser rejection boundaries, independent of DHCP wire input."""
import copy
import json
from pathlib import Path
import sys
import tempfile
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from dhcp_profile import load_dhcp_profile, write_dhcp_header
base = json.loads((ROOT / 'tests/fixtures/network/dhcp_profile.json').read_text())
changes = [('revision', True), ('revision', 2), ('pci_instance', False), ('pci_instance', 0),
           ('acquisition_seconds', 0), ('acquisition_seconds', 61), ('max_lease_seconds', 0xffffffff),
           ('subnet', '10.0.2.1/24'), ('subnet', '10.0.2.0/31'), ('addresses', ['10.0.2.15']),
           ('addresses', ['10.0.2.16', '10.0.2.15']), ('addresses', ['10.0.2.0', '10.0.2.15']),
           ('addresses', ['10.0.2.15', '10.0.3.15']), ('servers', []), ('servers', ['10.0.2.15']),
           ('servers', ['10.0.2.2', '10.0.2.2']), ('servers', ['10.0.3.2']),
           ('resolvers', ['127.0.0.1']), ('resolvers', ['224.0.0.1']), ('gateways', ['10.0.2.255']),
           ('egress', [{'cidr': '10.0.2.2/32', 'protocol': 'icmp', 'ports': [1, 1]}])]
with tempfile.TemporaryDirectory(prefix='dhcp_profile_') as temporary:
    path = Path(temporary) / 'profile.json'
    path.write_text(json.dumps(base)); parsed = load_dhcp_profile(path)
    write_dhcp_header(parsed, Path(temporary) / 'include')
    for field, value in changes:
        candidate = copy.deepcopy(base); candidate[field] = value; path.write_text(json.dumps(candidate))
        try:
            load_dhcp_profile(path)
        except ValueError:
            continue
        raise AssertionError('accepted invalid field ' + field)
    for text in ('{"revision":1,"revision":1}', json.dumps(dict(base, fallback='static')), ' ' * 4097):
        path.write_text(text)
        try:
            load_dhcp_profile(path)
        except ValueError:
            continue
        raise AssertionError('accepted malformed profile')
print('DHCP_PROFILE_NEGATIVES_PASSED=' + str(len(changes) + 3))
