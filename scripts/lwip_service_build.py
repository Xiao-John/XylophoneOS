# SPDX-License-Identifier: Apache-2.0
"""Build the optional, pinned NO_SYS network service without downloading inputs."""
import hashlib
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


def configuration(root, dns_probe=False):
    archive = os.environ.get("XOS_LWIP_SOURCE_ARCHIVE")
    if not archive:
        if dns_probe:
            raise SystemExit("The DNS probe requires XOS_LWIP_SOURCE_ARCHIVE")
        return {"enabled": False, "wire_version": 2, "guest_qualification": "not_run"}
    lock = json.loads((root / "src/ports/lwip/source_lock.json").read_text())
    digest = hashlib.sha256(Path(archive).read_bytes()).hexdigest()
    if digest != lock["sha256"]:
        raise SystemExit("Network service lwIP archive differs from source_lock.json")
    return {"enabled": True, "wire_version": 2, "lwip_version": lock["version"],
            "archive_sha256": digest, "patches": source_patches(root),
            "guest_qualification": "not_run", **({"dns_probe": True} if dns_probe else {})}


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


def build(root, output, sdk, run, tool, isa_flags, dns_probe=False):
    config = configuration(root, dns_probe)
    if not config["enabled"]:
        return [], (), config
    work = output / "net_lwip"
    source = prepare_source(root, os.environ["XOS_LWIP_SOURCE_ARCHIVE"], work / "source")
    include_flags = ("-I", str(root / "src/user/network/include"),
                     "-I", str(root / "src/ports/lwip/include"), "-I", str(source / "src/include"),
                     *(('-DXOS_NET_DNS_PROBE=1',) if dns_probe else ()))
    flags = ["-std=c11", "-Os", "-ffreestanding", "-fno-stack-protector", "-fno-pie", "-fno-pic",
             "-ffunction-sections", "-fdata-sections", "-fno-asynchronous-unwind-tables", "-fno-unwind-tables",
             *isa_flags, "-I", str(sdk / "include"), *include_flags,
             "-ffile-prefix-map=" + str(root) + "=."]
    sources = [source / "src/core" / name for name in core_sources]
    if dns_probe:
        sources.append(source / "src/core/dns.c")
    sources += [source / "src/core/ipv4" / name for name in ipv4_sources]
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
