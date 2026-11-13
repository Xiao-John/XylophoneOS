#!/usr/bin/env python3
"""Build and pack zlib (libz.a + minigzip) for XOS from a local archive (offline)."""
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
        raise SystemExit(f"ports/zlib: {name} is required")
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
        raise SystemExit("ports/zlib: source archive hash differs from source_lock.json")
    for name in ("manifest.json", "user.ld", "crt0_posix.o"):
        if not (sdk / name).is_file():
            raise SystemExit(f"ports/zlib: SDK is missing {name}")

    sys.path.insert(0, str(HERE.parents[2] / "scripts"))
    from xos_app import tree_receipt
    sdk_tree_sha256 = tree_receipt(sdk)[0]
    profile_name = port["package"]["target_profile"].replace("-", "_") + ".json"
    profile_path = HERE.parents[2] / "config/package" / profile_name
    if profile_path.is_file():
        registered = json.loads(profile_path.read_text()).get("sdk_tree_sha256", [])
        if sdk_tree_sha256 not in registered and os.environ.get("XOS_SDK_UNREGISTERED_OK") != "1":
            raise SystemExit("ports/zlib: SDK tree is not registered for the target profile")

    cc = shutil.which("x86_64-elf-gcc")
    ar = shutil.which("x86_64-elf-ar")
    objcopy = shutil.which("x86_64-elf-objcopy")
    if not cc or not ar or not objcopy:
        raise SystemExit("ports/zlib: x86_64-elf-gcc/ar/objcopy must be on PATH")
    libgcc = subprocess.check_output([cc, "-print-libgcc-file-name"], text=True).strip()

    work = Path(tempfile.mkdtemp(prefix="zlib_build_", dir=out))
    with tarfile.open(archive) as tar:
        tar.extractall(work, filter="data")
    source = work / f"zlib-{lock['version']}"
    if not (source / "zlib.h").is_file():
        raise SystemExit("ports/zlib: unexpected archive layout")

    cflags = ("-O2 -mno-red-zone -fno-pie -fno-pic -fno-stack-protector "
              f"-idirafter {sdk}/include")
    env = dict(os.environ)
    env.update({"CHOST": "x86_64-elf", "CC": cc,
                "CFLAGS": cflags, "AR": ar, "RANLIB": "x86_64-elf-ranlib"})
    run(["./configure", "--static"], cwd=source, env=env)
    run(["make", "-j4", "libz.a"], cwd=source, env=env)

    link = ["-nostdlib", "-static", "-no-pie", "-T", str(sdk / "user.ld"),
            str(sdk / "crt0_posix.o"), "-Wl,--start-group",
            str(sdk / "lib/libxos.a"), str(sdk / "lib/libxos_loader.a"),
            str(sdk / "lib/libc.a"), str(sdk / "lib/libm.a"), libgcc,
            "-Wl,--end-group"]
    binary_source = work / "minigzip"
    run([cc, *cflags.split(), "-I", str(source), str(source / "test/minigzip.c"),
         str(source / "libz.a"), *link, "-o", str(binary_source)])

    tree = out / "tree"
    if tree.exists():
        shutil.rmtree(tree)
    bindir = tree / "usr/bin"
    bindir.mkdir(parents=True)
    run([objcopy, "--strip-all", str(binary_source), str(bindir / "minigzip")])
    (tree / "usr/lib").mkdir()
    shutil.copyfile(source / "libz.a", tree / "usr/lib/libz.a")
    share = tree / "usr/share/zlib"
    (share / "include").mkdir(parents=True)
    shutil.copyfile(source / "zlib.h", share / "include/zlib.h")
    shutil.copyfile(source / "zconf.h", share / "include/zconf.h")
    (share / "samples").mkdir()
    shutil.copyfile(HERE / "samples/sample.txt", share / "samples/sample.txt")
    package = port["package"]["id"]
    license_dir = tree / f"usr/share/licenses/{package}"
    license_dir.mkdir(parents=True)
    shutil.copyfile(source / "LICENSE", license_dir / "LICENSE")

    provenance = {
        "package": package, "upstream": port["name"], "version": lock["version"],
        "license": port["license"], "archive": lock["archive"],
        "archive_sha256": lock["sha256"], "archive_mirror": lock["url"],
        "sha256_scope": lock.get("sha256_scope", "upstream_release"),
        "notes": "upstream zero patch; static libz.a and minigzip",
        "build": {"approach": "upstream configure --static + make libz.a",
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
        "binaries": [{"path": "usr/bin/minigzip",
                      "sha256": sha256(bindir / "minigzip"),
                      "size": (bindir / "minigzip").stat().st_size}],
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
                      "role": "executable" if relative == "usr/bin/minigzip" else "data"})
    manifest = {
        "format_version": 1, "id": package, "upstream_version": lock["version"], "revision": 0,
        "target_profile": port["package"]["target_profile"],
        "required_features": ["stdio", "heap", "file_io"], "runtime_dependencies": [],
        "files": files,
        "licenses": [f"usr/share/licenses/{package}/LICENSE"],
        "build_receipt": {"path": "usr/share/zlib/build_receipt.json",
                          "sha256": sha256(receipt_path)},
        "source": f"{lock['archive']} sha256 {lock['sha256']} ({lock['url']}); "
                  "provenance in usr/share/zlib/source.json",
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
