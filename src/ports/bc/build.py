#!/usr/bin/env python3
"""Build and pack GNU bc/dc for XOS from a local archive (offline)."""
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
        raise SystemExit(f"ports/bc: {name} is required")
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
        raise SystemExit("ports/bc: source archive hash differs from source_lock.json")
    for name in ("manifest.json", "user.ld", "crt0_posix.o"):
        if not (sdk / name).is_file():
            raise SystemExit(f"ports/bc: SDK is missing {name}")

    sys.path.insert(0, str(HERE.parents[2] / "scripts"))
    from xos_app import tree_receipt
    sdk_tree_sha256 = tree_receipt(sdk)[0]

    cc = shutil.which("x86_64-elf-gcc")
    objcopy = shutil.which("x86_64-elf-objcopy")
    if not cc or not objcopy:
        raise SystemExit("ports/bc: x86_64-elf-gcc/objcopy must be on PATH")
    libgcc = subprocess.check_output([cc, "-print-libgcc-file-name"], text=True).strip()

    work = Path(tempfile.mkdtemp(prefix="bc_build_", dir=out))
    with tarfile.open(archive) as tar:
        tar.extractall(work, filter="data")
    source = work / f"bc-{lock['version']}"
    if not (source / "configure").is_file():
        raise SystemExit("ports/bc: unexpected archive layout")

    cflags = ("-O2 -mno-red-zone -fno-pie -fno-pic -fno-stack-protector "
              f"-idirafter {sdk}/include")
    env = dict(os.environ)
    env.update({
        "CC": cc,
        "CFLAGS": cflags,
        "LDFLAGS": f"-nostdlib -static -no-pie -T {sdk}/user.ld {sdk}/crt0_posix.o",
        "LIBS": (f"-Wl,--start-group {sdk}/lib/libxos.a {sdk}/lib/libxos_loader.a "
                 f"{sdk}/lib/libc.a {sdk}/lib/libm.a {libgcc} -Wl,--end-group"),
    })
    run(["./configure", "--host=x86_64-elf", f"--build={subprocess.check_output(['uname', '-m'], text=True).strip()}-apple-darwin",
         "--without-readline", "--disable-nls", "--disable-dependency-tracking"],
        cwd=source, env=env)
    run(["make", "-j4"], cwd=source / "lib", env=env)
    for directory in ("bc", "dc"):
        run(["make", "-j4"], cwd=source / directory, env=env)

    tree = out / "tree"
    if tree.exists():
        shutil.rmtree(tree)
    bindir = tree / "usr/bin"
    bindir.mkdir(parents=True)
    for name in ("bc", "dc"):
        built = source / name / name
        if not built.is_file():
            raise SystemExit(f"ports/bc: build did not produce {name}")
        run([objcopy, "--strip-all", str(built), str(bindir / name)])
    share = tree / "usr/share/bc"
    (share / "samples").mkdir(parents=True)
    shutil.copyfile(HERE / "samples/calc.bc", share / "samples/calc.bc")
    shutil.copyfile(HERE / "samples/calc.dc", share / "samples/calc.dc")
    package = port["package"]["id"]
    license_dir = tree / f"usr/share/licenses/{package}"
    license_dir.mkdir(parents=True)
    shutil.copyfile(source / "COPYING", license_dir / "COPYING")

    provenance = {
        "package": package,
        "upstream": port["name"],
        "version": lock["version"],
        "license": port["license"],
        "archive": lock["archive"],
        "archive_sha256": lock["sha256"],
        "archive_mirror": lock["url"],
        "sha256_scope": lock.get("sha256_scope", "upstream_release"),
        "notes": "upstream zero patch; readline and NLS disabled",
        "build": {
            "approach": "autotools cross configure + make bc dc (no upstream patch)",
            "sdk": sdk.name,
            "sdk_build_id": (json.loads((sdk / "manifest.json").read_text()).get("build_id")
                             or json.loads((sdk / "manifest.json").read_text()).get("profile", "")),
            "sdk_tree_sha256": sdk_tree_sha256,
            "compiler": subprocess.check_output([cc, "--version"], text=True).splitlines()[0],
            "strip": "x86_64-elf-objcopy --strip-all bc dc",
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
        "binaries": [{"path": f"usr/bin/{name}", "sha256": sha256(bindir / name),
                      "size": (bindir / name).stat().st_size} for name in ("bc", "dc")],
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
                      "role": "executable" if relative in ("usr/bin/bc", "usr/bin/dc") else "data"})
    manifest = {
        "format_version": 1,
        "id": package,
        "upstream_version": lock["version"],
        "revision": 0,
        "target_profile": port["package"]["target_profile"],
        "required_features": ["stdio", "heap", "file_io"],
        "runtime_dependencies": [],
        "files": files,
        "licenses": [f"usr/share/licenses/{package}/COPYING"],
        "build_receipt": {"path": "usr/share/bc/build_receipt.json",
                          "sha256": sha256(receipt_path)},
        "source": f"{lock['archive']} sha256 {lock['sha256']} ({lock['url']}); "
                  "provenance in usr/share/bc/source.json",
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
