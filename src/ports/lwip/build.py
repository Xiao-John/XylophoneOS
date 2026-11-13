#!/usr/bin/env python3
"""Build lwIP (NO_SYS) and a raw-frame ICMP probe for XOS (offline)."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

CORE = [
    "init.c", "def.c", "inet_chksum.c", "ip.c", "mem.c", "memp.c", "netif.c",
    "pbuf.c", "raw.c", "stats.c", "sys.c", "tcp.c", "tcp_in.c", "tcp_out.c",
    "timeouts.c", "udp.c",
]
IPV4 = ["etharp.c", "icmp.c", "ip4.c", "ip4_addr.c", "ip4_frag.c"]


def need(name):
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"ports/lwip: {name} is required")
    return Path(value).resolve()


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command, cwd=None, env=None):
    print("+", " ".join(str(item) for item in command))
    subprocess.run(command, cwd=cwd, env=env, check=True)


def main():
    port = json.loads((HERE / "port.json").read_text())
    lock = json.loads((HERE / "source_lock.json").read_text())
    sdk = need("XOS_SDK")
    archive = need("XOS_SOURCE_ARCHIVE")
    out = need("XOS_OUT")
    out.mkdir(parents=True, exist_ok=True)
    output = out / f"{port['package']['id']}-{lock['version']}.xpk"
    receipt_output = out / "build_receipt.json"
    output.unlink(missing_ok=True)
    receipt_output.unlink(missing_ok=True)
    if sha256(archive) != lock["sha256"]:
        raise SystemExit("ports/lwip: source archive hash differs from source_lock.json")
    for name in ("manifest.json", "user.ld", "crt0_posix.o"):
        if not (sdk / name).is_file():
            raise SystemExit(f"ports/lwip: SDK is missing {name}")

    sys.path.insert(0, str(HERE.parents[2] / "scripts"))
    from xos_app import tree_receipt
    sdk_tree_sha256 = tree_receipt(sdk)[0]

    cc = shutil.which("x86_64-elf-gcc")
    cxx = shutil.which("x86_64-elf-g++")
    ar = shutil.which("x86_64-elf-ar")
    objcopy = shutil.which("x86_64-elf-objcopy")
    if not all((cc, cxx, ar, objcopy)):
        raise SystemExit("ports/lwip: x86_64-elf gcc/g++/ar/objcopy must be on PATH")
    libgcc = subprocess.check_output([cxx, "-print-libgcc-file-name"], text=True).strip()

    work = Path(tempfile.mkdtemp(prefix="lwip_build_", dir=out))
    with tarfile.open(archive) as tar:
        tar.extractall(work, filter="data")
    source = work / f"lwip-{lock['version']}"
    includes = source / "src/include"
    if not (includes / "lwip/init.h").is_file():
        raise SystemExit("ports/lwip: unexpected archive layout")

    cflags = ["-O2", "-mno-red-zone", "-fno-pie", "-fno-pic", "-fno-stack-protector",
              "-idirafter", str(sdk / "include"), "-I", str(includes),
              "-I", str(HERE / "include"), "-w"]
    objects = []
    for name in CORE:
        target = work / (Path(name).stem + ".o")
        run([cc, *cflags, "-c", str(source / "src/core" / name), "-o", str(target)])
        objects.append(str(target))
    for name in IPV4:
        target = work / ("ipv4_" + Path(name).stem + ".o")
        run([cc, *cflags, "-c", str(source / "src/core/ipv4" / name), "-o", str(target)])
        objects.append(str(target))
    ethernet = work / "ethernet.o"
    run([cc, *cflags, "-c", str(source / "src/netif/ethernet.c"), "-o", str(ethernet)])
    objects.append(str(ethernet))

    library = work / "liblwip.a"
    run([ar, "rcsD", str(library), *objects])

    cxxflags = ["-std=c++20", "-O2", "-g", "-ffreestanding", "-fno-exceptions", "-fno-rtti",
                "-fno-threadsafe-statics", "-fno-use-cxa-atexit", "-fno-unwind-tables",
                "-fno-asynchronous-unwind-tables", "-fno-stack-protector", "-fno-pic",
                "-fno-pie", "-mno-red-zone", "-nostdinc++",
                "-idirafter", str(sdk / "include"), "-I", str(includes),
                "-I", str(HERE / "include")]
    link = ["-nostdlib", "-static", "-no-pie", "-T", str(sdk / "user.ld"),
            str(sdk / "crt0_posix.o"), "-Wl,--start-group",
            str(library), str(sdk / "lib/libxos.a"), str(sdk / "lib/libxos_loader.a"),
            str(sdk / "lib/libc.a"), str(sdk / "lib/libm.a"), libgcc,
            "-Wl,--end-group"]
    binary_source = work / "net_ping"
    run([cxx, *cxxflags, str(HERE / "net_ping.cpp"), *link, "-o", str(binary_source)])

    tree = out / "tree"
    if tree.exists():
        shutil.rmtree(tree)
    bindir = tree / "usr/bin"
    bindir.mkdir(parents=True)
    run([objcopy, "--strip-all", str(binary_source), str(bindir / "net_ping")])
    (tree / "usr/lib").mkdir()
    shutil.copyfile(library, tree / "usr/lib/liblwip.a")
    share = tree / "usr/share/lwip"
    headers = share / "include"
    (headers / "arch").mkdir(parents=True)
    shutil.copyfile(HERE / "include/lwipopts.h", headers / "lwipopts.h")
    shutil.copyfile(HERE / "include/arch/cc.h", headers / "arch/cc.h")
    shutil.copyfile(HERE / "include/xos_lwip.h", headers / "xos_lwip.h")
    shutil.copytree(includes / "lwip", headers / "lwip")
    shutil.copytree(includes / "netif", headers / "netif")
    (share / "samples").mkdir()
    shutil.copyfile(HERE / "samples/sample.txt", share / "samples/sample.txt")
    package = port["package"]["id"]
    license_dir = tree / f"usr/share/licenses/{package}"
    license_dir.mkdir(parents=True)
    shutil.copyfile(source / "COPYING", license_dir / "COPYING")

    provenance = {
        "package": package, "upstream": port["name"], "version": lock["version"],
        "license": port["license"], "archive": lock["archive"],
        "archive_sha256": lock["sha256"], "archive_mirror": lock["url"],
        "sha256_scope": lock.get("sha256_scope", "upstream_release"),
        "notes": "NO_SYS=1; raw-frame net service as link layer; ICMP probe",
        "build": {"approach": "compile core+ipv4+ethernet into liblwip.a",
                  "sdk": sdk.name,
                  "sdk_build_id": (json.loads((sdk / "manifest.json").read_text()).get("build_id")
                                   or json.loads((sdk / "manifest.json").read_text()).get("profile", "")),
                  "sdk_tree_sha256": sdk_tree_sha256,
                  "compiler": subprocess.check_output([cc, "--version"], text=True).splitlines()[0]},
    }
    (share / "source.json").write_text(json.dumps(provenance, indent=2) + "\n")
    receipt = {
        "format_version": 1, "package_id": package, "upstream_version": lock["version"],
        "revision": 0, "status": "cross_built_guest_not_run",
        "recipe_sha256": sha256(HERE / "build.py"), "sdk": provenance["build"],
        "input": {"archive": lock["archive"], "sha256": lock["sha256"]},
        "binaries": [{"path": "usr/bin/net_ping", "sha256": sha256(bindir / "net_ping"),
                      "size": (bindir / "net_ping").stat().st_size}],
    }
    receipt_path = share / "build_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")

    for candidate in (sdk / "tools", HERE.parents[2] / "scripts"):
        if (candidate / "xypm_format.py").is_file():
            sys.path.insert(0, str(candidate))
            break
    import xypm_format  # noqa: E402

    files = []
    for path in sorted(p for p in tree.rglob("*") if p.is_file()):
        relative = path.relative_to(tree).as_posix()
        files.append({"path": relative, "type": "file", "size": path.stat().st_size,
                      "sha256": sha256(path),
                      "role": "executable" if relative == "usr/bin/net_ping" else "data"})
    manifest = {
        "format_version": 1, "id": package, "upstream_version": lock["version"], "revision": 0,
        "target_profile": port["package"]["target_profile"],
        "required_features": ["stdio", "heap", "file_io"], "runtime_dependencies": [],
        "files": files,
        "licenses": [f"usr/share/licenses/{package}/COPYING"],
        "build_receipt": {"path": "usr/share/lwip/build_receipt.json",
                          "sha256": sha256(receipt_path)},
        "source": f"{lock['archive']} sha256 {lock['sha256']} ({lock['url']}); "
                  "provenance in usr/share/lwip/source.json",
    }
    result = xypm_format.pack_package(tree, manifest, output)
    final = dict(receipt, status="packed_guest_not_run",
                 outputs={"xpk": output.name, "sha256": result["sha256"]})
    receipt_output.write_text(json.dumps(final, indent=2, sort_keys=True) + "\n")
    shutil.rmtree(work)
    print(json.dumps({"xpk": str(output), "sha256": result["sha256"],
                      "files": result["payload_files"]}, indent=2))


if __name__ == "__main__":
    main()
