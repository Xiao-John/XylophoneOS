#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compile one explicit HTTPS origin and DER CA into the bounded broker policy."""
from hashlib import sha256
import ipaddress
import re


def write_policy(origin, ipv4, anchor_path, output):
    match = re.fullmatch(r'https://([a-z0-9.-]+)(?::([0-9]{1,5}))?', origin)
    if not match: raise ValueError('select an explicit lowercase DNS HTTPS origin')
    host, port_text = match.groups(); port = int(port_text or 443)
    if not 1 <= port <= 65535 or len(host) > 253 or '.' not in host or not all(
        re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', part) for part in host.split('.')):
        raise ValueError('invalid HTTPS origin')
    address = ipaddress.IPv4Address(ipv4)
    anchor = anchor_path.read_bytes()
    if not 1 <= len(anchor) <= 4096 or anchor[0] != 0x30:
        raise ValueError('select a bounded DER CA trust anchor')
    output.write_text('#pragma once\nstatic constexpr char clarke_tls_host[] = "' + host + '";\n'
        'static constexpr unsigned clarke_tls_port = ' + str(port) + ';\n'
        'static constexpr unsigned clarke_tls_address = ' + str(int(address)) + ';\n'
        'static constexpr unsigned char clarke_tls_anchor[] = {' + ','.join(map(str,anchor)) + '};\n')
    return {'origin':origin, 'ipv4_address':str(address), 'host':host, 'port':port,
            'ca_sha256':sha256(anchor).hexdigest(), 'minimum_tls':'1.2',
            'verify_chain':True, 'verify_hostname':True, 'require_close_notify':True}
