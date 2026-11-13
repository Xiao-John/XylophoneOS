#!/usr/bin/env python3
"""Build and pack NASM for XOS from a local archive and a frozen SDK (offline)."""
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


def need(name):
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"ports/nasm: {name} is required")
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

    if sha256(archive) != lock["sha256"]:
        raise SystemExit("ports/nasm: source archive hash differs from source_lock.json")
    for name in ("manifest.json", "user.ld", "crt0_posix.o"):
        if not (sdk / name).is_file():
            raise SystemExit(f"ports/nasm: SDK is missing {name}")

    work = Path(tempfile.mkdtemp(prefix="nasm_build_", dir=out))
    with tarfile.open(archive) as tar:
        tar.extractall(work, filter="data")
    source = work / f"nasm-{lock['version']}"
    if not (source / "configure").is_file():
        raise SystemExit("ports/nasm: unexpected archive layout")

    compiler = shutil.which("x86_64-elf-gcc")
    objcopy = shutil.which("x86_64-elf-objcopy")
    if compiler is None or objcopy is None:
        raise SystemExit("ports/nasm: x86_64-elf-gcc and x86_64-elf-objcopy must be on PATH")
    machine = subprocess.check_output([compiler, "-dumpmachine"], text=True).strip()
    if machine != "x86_64-elf":
        raise SystemExit(f"ports/nasm: compiler targets {machine}, expected x86_64-elf")

    libgcc = subprocess.check_output([compiler, "-print-libgcc-file-name"], text=True).strip()
    loader = sdk / "lib/libxos_loader.a"
    env = dict(os.environ)
    env["CC"] = compiler
    run(["./configure", "--host=x86_64-elf", f"--build={os.uname().machine}-apple-darwin",
         f"CFLAGS=-O2 -mno-red-zone -fno-pie -fno-pic -fno-stack-protector -idirafter {sdk}/include",
         f"LDFLAGS=-nostdlib -static -no-pie -T {sdk}/user.ld {sdk}/crt0_posix.o",
         f"LIBS=-Wl,--start-group {sdk}/lib/libxos.a {sdk}/lib/libxos_loader.a "
         f"{sdk}/lib/libc.a {sdk}/lib/libm.a {libgcc} -Wl,--end-group"],
        cwd=source, env=env)
    run(["make", "-j4", "nasm", "ndisasm"], cwd=source, env=env)

    tree = out / "tree"
    if tree.exists():
        shutil.rmtree(tree)
    binary = tree / "usr/bin/nasm"
    binary.parent.mkdir(parents=True)
    run([objcopy, "--strip-all", source / "nasm", binary])
    disassembler = tree / "usr/bin/ndisasm"
    run([objcopy, "--strip-all", source / "ndisasm", disassembler])
    package = port["package"]["id"]
    license_dir = tree / f"usr/share/licenses/{package}"
    license_dir.mkdir(parents=True)
    shutil.copyfile(source / "LICENSE", license_dir / "LICENSE")
    share = tree / "usr/share/nasm"
    share.mkdir(parents=True)
    for sample in sorted((HERE / "samples").glob("*.asm")):
        shutil.copyfile(sample, share / sample.name)

    provenance = {
        "package": package,
        "upstream": port["name"],
        "version": lock["version"],
        "license": port["license"],
        "archive": lock["archive"],
        "archive_sha256": lock["sha256"],
        "archive_mirror": lock["url"],
        "upstream_site": lock.get("upstream_site"),
        "sha256_scope": lock.get("sha256_scope", "upstream_release"),
        "build": {
            "approach": "upstream autotools configure + make with the frozen XOS SDK",
            "sdk": sdk.name,
            "sdk_build_id": json.loads((sdk / "manifest.json").read_text())["build_id"],
            "compiler": subprocess.check_output([compiler, "--version"], text=True).splitlines()[0],
            "configure": "see build.py: CFLAGS/LDFLAGS/LIBS pin SDK crt0, user.ld and static libs",
            "strip": "x86_64-elf-objcopy --strip-all",
        },
    }
    (share / "source.json").write_text(json.dumps(provenance, indent=2) + "\n")

    receipt = {
        "format_version": 1,
        "package_id": package,
        "upstream_version": lock["version"],
        "revision": 0,
        "status": "cross_built_guest_not_run",
        "recipe_sha256": sha256(HERE / "build.py"),
        "sdk": provenance["build"],
        "input": {"archive": lock["archive"], "sha256": lock["sha256"]},
        "binaries": [
            {"path": "usr/bin/nasm", "sha256": sha256(binary), "size": binary.stat().st_size},
            {"path": "usr/bin/ndisasm", "sha256": sha256(disassembler),
             "size": disassembler.stat().st_size},
        ],
        "outputs": {},
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
                      "role": "executable"
                      if relative in ("usr/bin/nasm", "usr/bin/ndisasm") else "data"})
    license_path = f"usr/share/licenses/{package}/LICENSE"
    manifest = {
        "format_version": 1,
        "id": package,
        "upstream_version": lock["version"],
        "revision": 0,
        "target_profile": port["package"]["target_profile"],
        "required_features": ["stdio", "heap", "file_io", "directories"],
        "runtime_dependencies": [],
        "files": files,
        "licenses": [license_path],
        "build_receipt": {"path": "usr/share/nasm/build_receipt.json",
                          "sha256": sha256(receipt_path)},
        "source": f"{lock['archive']} sha256 {lock['sha256']} ({lock['url']}); "
                  "build provenance in usr/share/nasm/source.json",
    }
    output = out / f"{package}-{lock['version']}.xpk"
    output.unlink(missing_ok=True)
    result = xypm_format.pack_package(tree, manifest, output)

    final = dict(receipt, status="packed_guest_not_run",
                 outputs={"xpk": output.name, "sha256": result["sha256"]})
    (out / "build_receipt.json").write_text(json.dumps(final, indent=2, sort_keys=True) + "\n")
    shutil.rmtree(work)
    print(json.dumps({"xpk": str(output), "sha256": result["sha256"],
                      "files": result["payload_files"]}, indent=2))


if __name__ == "__main__":
    main()
