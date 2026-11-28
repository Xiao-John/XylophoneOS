# SPDX-License-Identifier: Apache-2.0
"""Strict compiler-sealed DHCP installation input; never a runtime RPC grant."""
import hashlib
import ipaddress
import json


def load_dhcp_profile(path):
    data = path.read_bytes()
    if len(data) > 4096:
        raise ValueError("DHCP installation profile exceeds 4096 bytes")

    def unique(pairs):
        result = dict(pairs)
        if len(result) != len(pairs):
            raise ValueError("Duplicate DHCP installation field")
        return result

    profile = json.loads(data, object_pairs_hook=unique)
    expected = {"revision", "pci_instance", "subnet", "addresses", "servers", "gateways", "resolvers",
                "max_lease_seconds", "acquisition_seconds", "egress"}
    if not isinstance(profile, dict) or set(profile) != expected or type(profile["revision"]) is not int or profile["revision"] != 1:
        raise ValueError("Expected exactly the revision 1 DHCP installation fields")
    for field, minimum, maximum in (("pci_instance", 1, 65536), ("max_lease_seconds", 1, 0xfffffffe),
                                    ("acquisition_seconds", 1, 60)):
        if type(profile[field]) is not int or not minimum <= profile[field] <= maximum:
            raise ValueError(f"Invalid DHCP {field}")
    if not isinstance(profile["subnet"], str):
        raise ValueError("DHCP subnet must be canonical IPv4 CIDR")
    subnet = ipaddress.IPv4Network(profile["subnet"], strict=True)
    if str(subnet) != profile["subnet"] or not 1 <= subnet.prefixlen <= 30:
        raise ValueError("DHCP subnet must be canonical and contain usable hosts")

    def address(text, local=False):
        if not isinstance(text, str):
            raise ValueError("DHCP address must be a canonical IPv4 string")
        value = ipaddress.IPv4Address(text)
        first = int(value) >> 24
        if str(value) != text or not first or first == 127 or first >= 224:
            raise ValueError("DHCP address must be unicast")
        if local and (value not in subnet or value in (subnet.network_address, subnet.broadcast_address)):
            raise ValueError("DHCP peer/address must be a host on the sealed subnet")
        return int(value)

    offered = profile["addresses"]
    if not isinstance(offered, list) or len(offered) != 2:
        raise ValueError("DHCP addresses must be an inclusive pair")
    first, last = (address(value, True) for value in offered)
    if first > last:
        raise ValueError("DHCP address range is reversed")
    for name in ("servers", "gateways", "resolvers"):
        values = profile[name]
        if not isinstance(values, list) or not (1 if name == "servers" else 0) <= len(values) <= 2:
            raise ValueError("DHCP authority lists allow at most two peers and require a server")
        peers = [address(value, name != "resolvers") for value in values]
        if len(set(peers)) != len(peers) or any(first <= value <= last for value in peers):
            raise ValueError("DHCP authority peers must be distinct and outside the offer range")
    from lwip_service_build import validate_egress
    validate_egress(profile["egress"])
    return dict(profile, source_sha256=hashlib.sha256(data).hexdigest())


def write_dhcp_header(profile, directory):
    subnet = ipaddress.IPv4Network(profile["subnet"])
    def ip(value):
        return str(int(ipaddress.IPv4Address(value))) + "u"
    def peers(name):
        return "{" + ", ".join([*(ip(value) for value in profile[name]), *("0u" for _ in range(2 - len(profile[name])))]) + "}, " + str(len(profile[name]))
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "xos_net_dhcp_profile.hpp").write_text(
        "// Generated from the trusted installation profile.\n#pragma once\n"
        "namespace xos::user::network {\ninline constexpr dhcp::policy installed_dhcp_policy{\n" +
        f"{int(subnet.network_address)}u, {int(subnet.netmask)}u, " + ", ".join(ip(value) for value in profile["addresses"]) + ",\n" +
        ",\n".join(peers(name) for name in ("servers", "gateways", "resolvers")) + ",\n" + str(profile["max_lease_seconds"]) + "u};\n" +
        f"inline constexpr u64 installed_acquisition_ns = {profile['acquisition_seconds']}ull * 1'000'000'000ull;\n" + "}\n")
