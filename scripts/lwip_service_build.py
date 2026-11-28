# SPDX-License-Identifier: Apache-2.0
"""Build the optional, pinned NO_SYS network service without downloading inputs."""
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

core_sources = ["init.c", "def.c", "inet_chksum.c", "ip.c", "mem.c", "memp.c", "netif.c",
                "pbuf.c", "raw.c", "stats.c", "sys.c", "tcp.c", "tcp_in.c", "tcp_out.c",
                "timeouts.c", "udp.c"]
ipv4_sources = ["etharp.c", "icmp.c", "ip4.c", "ip4_addr.c", "ip4_frag.c"]


def load_static_profile(path):
    with path.open("rb") as stream:
        data = stream.read(4097)
    if len(data) > 4096:
        raise ValueError("Static network profile exceeds 4096 bytes")

    def unique_fields(pairs):
        result = dict(pairs)
        if len(result) != len(pairs):
            raise ValueError("Duplicate static network profile field")
        return result

    profile = json.loads(data, object_pairs_hook=unique_fields)
    if not isinstance(profile, dict) or type(profile.get("revision")) is not int:
        raise ValueError("Expected an integer static network profile revision")
    revision = profile["revision"]
    fields = {"revision", "pci_instance", "resolver"}
    if revision == 2:
        fields.add("egress")
    elif revision != 1 or len(data) > 512:
        raise ValueError("Expected revision 1 (at most 512 bytes) or revision 2")
    if set(profile) != fields:
        raise ValueError("Unexpected or missing static network profile fields")
    instance, address = profile["pci_instance"], profile["resolver"]
    if type(instance) is not int or not 1 <= instance <= 65536:
        raise ValueError("pci_instance must be 1 + PCI BDF")
    if not isinstance(address, str):
        raise ValueError("resolver must be a canonical IPv4 address")
    peer = ipaddress.IPv4Address(address)
    if (str(peer) != address or peer not in ipaddress.IPv4Network("10.0.2.0/24") or
            address in {"10.0.2.0", "10.0.2.15", "10.0.2.255"}):
        raise ValueError("resolver must be a peer on the admitted static IPv4 subnet")
    if revision == 2:
        validate_egress(profile["egress"])
    return dict(profile, source_sha256=hashlib.sha256(data).hexdigest())


def validate_egress(rules):
    """Trusted installation grants; DNS and DHCP never feed this parser."""
    if not isinstance(rules, list) or len(rules) > 8:
        raise ValueError("egress must be an array of at most 8 rules")
    seen = set()
    for rule in rules:
        if not isinstance(rule, dict) or set(rule) != {"cidr", "protocol", "ports"}:
            raise ValueError("Each egress rule needs cidr, protocol and ports")
        if not isinstance(rule["cidr"], str):
            raise ValueError("egress cidr must be canonical IPv4 network notation")
        network = ipaddress.IPv4Network(rule["cidr"], strict=True)
        if str(network) != rule["cidr"]:
            raise ValueError("egress cidr must include its canonical prefix")
        if rule["protocol"] not in ("tcp", "udp"):
            raise ValueError("egress protocol must be tcp or udp")
        ports = rule["ports"]
        if (not isinstance(ports, list) or len(ports) != 2 or
                any(type(port) is not int for port in ports) or
                not 1 <= ports[0] <= ports[1] <= 65535):
            raise ValueError("egress ports must be an inclusive interval in 1..65535")
        key = rule["cidr"], rule["protocol"], *ports
        if key in seen:
            raise ValueError("duplicate egress rule")
        seen.add(key)


def write_egress_header(rules, directory):
    validate_egress(rules)
    directory.mkdir(parents=True, exist_ok=True)
    rows = []
    for rule in rules:
        network = ipaddress.IPv4Network(rule["cidr"])
        rows.append("    {" + f"{int(network.network_address)}u, {network.prefixlen}u, " +
                    f"net2::protocol::{rule['protocol']}, {rule['ports'][0]}, {rule['ports'][1]}" + "}")
    body = ",\n".join(rows)
    (directory / "xos_net_egress_profile.hpp").write_text(
        "// Generated from the trusted installation profile.\n#pragma once\n"
        "namespace xos::user::network {\n"
        "inline constexpr egress_policy installed_egress_policy{{\n" + body +
        "\n}, " + str(len(rows)) + "};\n"
        "static_assert(valid_egress_policy(installed_egress_policy));\n}\n")


def configuration(root, dns_probe=False, static_profile=None, dhcp_profile=None):
    archive = os.environ.get("XOS_LWIP_SOURCE_ARCHIVE")
    if not archive:
        if dns_probe or static_profile or dhcp_profile:
            raise SystemExit("The resolver requires XOS_LWIP_SOURCE_ARCHIVE")
        return {"enabled": False, "wire_version": 2, "guest_qualification": "not_run"}
    lock = json.loads((root / "src/ports/lwip/source_lock.json").read_text())
    digest = hashlib.sha256(Path(archive).read_bytes()).hexdigest()
    if digest != lock["sha256"]:
        raise SystemExit("Network service lwIP archive differs from source_lock.json")
    return {"enabled": True, "wire_version": 2, "lwip_version": lock["version"],
            "archive_sha256": digest, "patches": source_patches(root),
            "guest_qualification": "not_run", **({"dns_probe": True} if dns_probe else {}),
            **({"static_profile": static_profile} if static_profile else {}),
            **({"dhcp_profile": dhcp_profile} if dhcp_profile else {})}


def source_patches(root):
    """Return and verify the tracked, ordered local changes to the raw archive."""
    port = root / "src/ports/lwip"
    entries = json.loads((port / "source_lock.json").read_text()).get("patches", [])
    for entry in entries:
        relative = Path(entry["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("lwIP patch path must remain under its port directory")
        if hashlib.sha256((port / relative).read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError(f"lwIP patch hash mismatch: {relative}")
        for name in entry["files"]:
            if Path(name).is_absolute() or ".." in Path(name).parts:
                raise ValueError("lwIP patched file must remain under its source directory")
    return entries


def source_input_paths(root):
    return [root / "src/ports/lwip/source_lock.json",
            *(root / "src/ports/lwip" / entry["path"] for entry in source_patches(root))]


def extract_source(archive, output, expected_sha256):
    data = Path(archive).read_bytes()
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError("lwIP archive hash mismatch")
    if output.is_symlink():
        raise ValueError("refusing a symlinked lwIP source output")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    # Extract the bytes already verified, avoiding a path replacement race.
    import io
    with tarfile.open(fileobj=io.BytesIO(data)) as archive_file:
        archive_file.extractall(output, filter="data")
    return output / "lwip-2.2.1"


def prepare_source(root, archive, output, *, patch_tool="patch", environment=None):
    """Verify pristine bytes, then apply exact local patches to a private copy.

    extract_source intentionally stays pristine for historical upstream audits.
    No download, fuzzy application, prepatched source, or fallback is accepted.
    """
    lock = json.loads((root / "src/ports/lwip/source_lock.json").read_text())
    patches = source_patches(root)
    source = extract_source(archive, output, lock["sha256"])
    for entry in patches:
        patch_bytes = (root / "src/ports/lwip" / entry["path"]).read_bytes()
        if hashlib.sha256(patch_bytes).hexdigest() != entry["sha256"]:
            raise ValueError("lwIP patch changed after verification")
        before = {str(path.relative_to(source)): hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in source.rglob("*") if path.is_file()}
        for name, digests in entry["files"].items():
            if before.get(name) != digests["before"]:
                raise ValueError(f"lwIP patch preimage mismatch: {name}")
        subprocess.run([patch_tool, "--batch", "--forward", "--fuzz=0", "--no-backup-if-mismatch", "-p1"],
                       input=patch_bytes, cwd=source, check=True, timeout=30,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment)
        after = {str(path.relative_to(source)): hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in source.rglob("*") if path.is_file()}
        expected = dict(before)
        expected.update({name: digests["after"] for name, digests in entry["files"].items()})
        if after != expected:
            raise ValueError(f"lwIP patch output differs from locked files: {entry['path']}")
    return source


def build(root, output, sdk, run, tool, isa_flags, dns_probe=False, static_profile=None, dhcp_profile=None):
    config = configuration(root, dns_probe, static_profile, dhcp_profile)
    if not config["enabled"]:
        return [], (), config
    work = output / "net_lwip"
    source = prepare_source(root, os.environ["XOS_LWIP_SOURCE_ARCHIVE"], work / "source")
    policy_flags = ()
    profile = dhcp_profile or static_profile
    if profile and "egress" in profile:
        write_egress_header(profile["egress"], work / "include")
        policy_flags = ("-DXOS_NET_EGRESS_PROFILE=1", "-I", str(work / "include"))
    if dhcp_profile:
        from dhcp_profile import write_dhcp_header
        write_dhcp_header(dhcp_profile, work / "include")
        policy_flags += ("-DXOS_NET_DHCP_PROFILE=1",)
    include_flags = ("-I", str(root / "src/user/network/include"),
                     "-I", str(root / "src/ports/lwip/include"), "-I", str(source / "src/include"),
                     *policy_flags,
                     *(("-DXOS_NET_DNS_PROBE=1",) if dns_probe else ()),
                     *((f"-DXOS_NET_STATIC_RESOLVER={int(ipaddress.IPv4Address(static_profile['resolver']))}u",)
                       if static_profile else ()))
    flags = ["-std=c11", "-Os", "-ffreestanding", "-fno-stack-protector", "-fno-pie", "-fno-pic",
             "-ffunction-sections", "-fdata-sections", "-fno-asynchronous-unwind-tables", "-fno-unwind-tables",
             *isa_flags, "-I", str(sdk / "include"), *include_flags,
             "-ffile-prefix-map=" + str(root) + "=."]
    sources = [source / "src/core" / name for name in core_sources]
    if dns_probe or static_profile or dhcp_profile:
        sources.append(source / "src/core/dns.c")
    sources += [source / "src/core/ipv4" / name for name in ipv4_sources]
    if dhcp_profile:
        sources += [source / "src/core/ipv4" / name for name in ("dhcp.c", "acd.c")]
    sources += [source / "src/netif/ethernet.c"]
    objects = []
    for item in sources:
        obj = work / (item.relative_to(source).as_posix().replace("/", "_") + ".o")
        run([tool("gcc"), *flags, "-c", str(item), "-o", str(obj)])
        objects.append(str(obj))
    license_file = source / "COPYING"
    if hashlib.sha256(license_file.read_bytes()).digest() != hashlib.sha256((root / "licenses/lwip.txt").read_bytes()).digest():
        raise ValueError("lwIP COPYING differs from registered notice")
    receipt = dict(config, sources={str(item.relative_to(source)): hashlib.sha256(item.read_bytes()).hexdigest()
                                   for item in sorted(source.rglob("*")) if item.is_file()})
    (output / "net_lwip_inputs.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return objects, include_flags, config
