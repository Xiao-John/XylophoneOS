# SPDX-License-Identifier: Apache-2.0
"""Build the optional, pinned NO_SYS network service without downloading inputs."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tarfile

core_sources = ["init.c", "def.c", "inet_chksum.c", "ip.c", "mem.c", "memp.c", "netif.c",
                "pbuf.c", "raw.c", "stats.c", "sys.c", "tcp.c", "tcp_in.c", "tcp_out.c",
                "timeouts.c", "udp.c"]
ipv4_sources = ["etharp.c", "icmp.c", "ip4.c", "ip4_addr.c", "ip4_frag.c"]


def configuration(root):
    archive = os.environ.get("XOS_LWIP_SOURCE_ARCHIVE")
    if not archive:
        return {"enabled": False, "wire_version": 2, "guest_qualification": "not_run"}
    lock = json.loads((root / "src/ports/lwip/source_lock.json").read_text())
    digest = hashlib.sha256(Path(archive).read_bytes()).hexdigest()
    if digest != lock["sha256"]:
        raise SystemExit("Network service lwIP archive differs from source_lock.json")
    return {"enabled": True, "wire_version": 2, "lwip_version": lock["version"],
            "archive_sha256": digest, "guest_qualification": "not_run"}


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


def build(root, output, sdk, run, tool, isa_flags):
    config = configuration(root)
    if not config["enabled"]:
        return [], (), config
    work = output / "net_lwip"
    source = extract_source(os.environ["XOS_LWIP_SOURCE_ARCHIVE"], work / "source", config["archive_sha256"])
    include_flags = ("-I", str(root / "src/user/network/include"),
                     "-I", str(root / "src/ports/lwip/include"), "-I", str(source / "src/include"))
    flags = ["-std=c11", "-Os", "-ffreestanding", "-fno-stack-protector", "-fno-pie", "-fno-pic",
             "-ffunction-sections", "-fdata-sections", "-fno-asynchronous-unwind-tables", "-fno-unwind-tables",
             *isa_flags, "-I", str(sdk / "include"), *include_flags,
             "-ffile-prefix-map=" + str(root) + "=."]
    sources = [source / "src/core" / name for name in core_sources]
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
