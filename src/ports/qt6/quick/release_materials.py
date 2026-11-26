#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Stage offline source and relinking materials for a verified Qt Quick kit."""

import argparse
import hashlib
from pathlib import Path, PurePosixPath
import shlex
import shutil
import subprocess
import sys
import tarfile

from quick_kit import ROOT, PORT, fingerprint
from relink import json_read, link_flags, manifest_file, require, sha, verified_manifest

sys.path.insert(0, str(ROOT / "scripts"))
from archive_member_map import read_archive
from xypm_format import canonical


qt_root = PORT.parent
locks = {"qtbase": qt_root / "source_lock.json", "qtdeclarative": qt_root / "qml/source_lock.json",
         "qtshadertools": PORT / "source_lock.json"}


def copy_file(source, output, name):
    destination = output / name
    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    require(sha(source) == sha(destination), "material changed during copy: " + name)


def check_declarative_snapshot(archive, record, kit):
    require(record["declarative_snapshot_sha256"] == sha(archive), "Qt Declarative snapshot differs from the build record")
    bindings = record["target_declarative_archives"]
    require(bindings.keys() == {"libQt6Quick.a", "libQt6Qml.a"} and
            all(sha(manifest_file(kit, "target/lib/" + name)) == digest for name, digest in bindings.items()),
            "Qt Declarative build record differs from the installed kit")
    prefix = record["declarative_snapshot_root"]
    require(prefix == "declarative_source", "unexpected Qt Declarative source root")
    required = {"CMakeLists.txt", "LICENSES/LGPL-3.0-only.txt", "src/qml/CMakeLists.txt",
                "src/quick/CMakeLists.txt", "src/3rdparty/masm/wtf/os_allocator_xos.cpp"}
    seen = set()
    with tarfile.open(archive, mode="r:xz") as stream:
        for member in stream:
            path = PurePosixPath(member.name)
            require(path.parts[:1] == (prefix,) and ".." not in path.parts and
                    (member.isfile() or member.isdir()), "unexpected Qt Declarative snapshot member")
            name = PurePosixPath(*path.parts[1:]).as_posix()
            require(name not in seen, "duplicate Qt Declarative snapshot member: " + name)
            seen.add(name)
            if name == "src/3rdparty/masm/wtf/os_allocator_xos.cpp":
                data = stream.extractfile(member).read()
                require(hashlib.sha256(data).hexdigest() == sha(qt_root / "qml/runtime/os_allocator_xos.cpp"),
                        "Qt Declarative snapshot differs from the Qt allocator overlay")
    require(required <= seen, "Qt Declarative source snapshot is incomplete")
    return len(seen)


def link_plan(args, receipt, output):
    build = args.application_build / "build"
    executable = manifest_file(args.application_build, receipt["elf"])
    require(sha(executable) == receipt["elf_sha256"], "application differs from its build receipt")
    target = executable.relative_to(build).as_posix()
    commands = subprocess.check_output(["ninja", "-C", str(build), "-t", "commands", target], text=True)
    tokens = shlex.split(commands.splitlines()[-1])
    require(tokens[:2] == [":", "&&"] and tokens[-2:] == ["&&", ":"] and
            PurePosixPath(tokens[2]).name == "x86_64-elf-g++", "unrecognized static Quick link step")
    require(tokens[3].startswith("--sysroot=") and
            tokens[3].endswith("/runtime/sdk/sysroot"), "unexpected Quick link sysroot")
    original_kit = PurePosixPath(tokens[3][len("--sysroot="):-len("/runtime/sdk/sysroot")])
    options = tokens[tokens.index("-static"):-2]
    outfile = options.index("-o")
    require(options[outfile + 1] == target, "Quick link output differs from its receipt")
    del options[outfile:outfile + 2]
    plan = []
    for option in options:
        if option in link_flags:
            plan.append(option)
            continue
        path = PurePosixPath(option)
        require(path.suffix in (".a", ".o", ".ld"), "unbound Quick link input: " + path.name)
        if path.is_absolute():
            name = path.relative_to(original_kit).as_posix()
            require(name.startswith(("target/", "runtime/sdk/sysroot/")), "link input is outside the target kit")
            source = manifest_file(args.kit, name)
            package_path = "link/kit/" + name
        else:
            source = manifest_file(build, path.as_posix())
            package_path = "link/application/" + path.as_posix()
        copy_file(source, output, package_path)
        plan.append({"file": package_path})
    (output / "link/plan.json").write_bytes(canonical(plan))


def stage(args):
    args.kit = args.kit.resolve(strict=True)
    args.application_build = args.application_build.resolve(strict=True)
    output = args.output.resolve()
    sources = (args.kit, args.application_build, args.application_source.resolve(strict=True), qt_root)
    require(not any(output.is_relative_to(path) for path in sources), "output is inside a materials input")
    kit_manifest = manifest_file(args.kit, "manifest.json")
    kit_digest = sha(kit_manifest)
    kit_format = fingerprint(args.kit)
    kit_format["input_application_receipt_sha256"] = sha(manifest_file(args.kit, "input_application_receipt.json"))
    require(json_read(kit_manifest) == kit_format, "the relocatable kit differs from its manifest")
    receipt_file = manifest_file(args.application_build, "receipt.json")
    receipt = json_read(receipt_file)
    require(receipt.get("status") == "static_quick_application_linked" and receipt.get("kit_manifest_sha256") == kit_digest
            and all(receipt.get(key) == kit_format[key] for key in ("qt_inputs", "sdk_manifest_sha256", "qtbase_source_sha256")),
            "application receipt belongs to a different Qt Quick kit")

    record_digest = sha(args.build_record)
    record = json_read(args.build_record)
    archives = {"qtbase": manifest_file(args.kit, "qtbase.tar.xz"),
                "qtdeclarative": args.qtdeclarative, "qtshadertools": args.qtshadertools}
    lock_records = {name: json_read(path) for name, path in locks.items()}
    provenance = {}
    for name, archive in archives.items():
        digest = sha(archive)
        expected = lock_records[name]["sha256"]
        if name == "qtdeclarative" and args.declarative_built_snapshot:
            count = check_declarative_snapshot(archive, record, args.kit)
            provenance[name] = {"mode": "observed_patched_source_tree", "sha256": digest,
                                "locked_upstream_sha256": expected, "snapshot_members": count}
        else:
            require(digest == expected, name + " source archive differs from the pinned upstream bytes")
            provenance[name] = {"mode": "locked_upstream_archive", "sha256": digest}

    output.mkdir(parents=True, exist_ok=False)
    try:
        for name, archive in archives.items():
            package_path = f"sources/{name}.tar.xz"
            copy_file(archive, output, package_path)
            require(sha(output / package_path) == provenance[name]["sha256"],
                    "source archive changed during staging: " + name)
        copy_file(args.build_record, output, "recipes/build_record.json")
        require(sha(output / "recipes/build_record.json") == record_digest, "build record changed during staging")
        copy_file(kit_manifest, output, "link/kit_manifest.json")
        copy_file(receipt_file, output, "link/application_receipt.json")
        copy_file(PORT / "relink.py", output, "relink.py")
        copy_file(PORT / "release_materials.md", output, "README.md")
        shutil.copytree(args.kit / "notices", output / "notices")
        for name in ("LICENSE", "NOTICE", "README.md", "profile.json", "sdk/manifest.json"):
            copy_file(manifest_file(args.kit, "runtime/" + name), output, "notices/runtime/" + name)
        for entry in ("src/ports/qt6", "src/shared/include", "src/user/include"):
            shutil.copytree(ROOT / entry, output / "recipes/xos" / entry,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for script in ("archive_member_map", "build_glibc_program", "glibc_g1_deps", "glibc_g1_probe",
                       "package_glibc_sdk", "verify_glibc_source", "xos_app", "xypm_format", "xypm_sdk_profile"):
            name = f"scripts/{script}.py"
            copy_file(ROOT / name, output, "recipes/xos/" + name)
        for doc in ("48bcc2f4_qt_e19_glibc_target_qtgui_packages", "a95b1a20_qt_e19_host_shader_generation",
                    "c8f43a1f_qt_e19_software_quick_guest_smoke", "b9673c26_qt_e19_external_quick_application_builder",
                    "d8bd3467_qt_e18_target_qml_and_vm", "8d6f3d2c_qt_e18_glibc_qtcore_target_build"):
            name = f"docs/work_log/{doc}.md"
            copy_file(ROOT / name, output, "recipes/xos/" + name)
        for name in ("LICENSE", "NOTICE"):
            copy_file(ROOT / name, output, "recipes/xos/" + name)
        for name in ("CMakeLists.txt", "Main.qml", "main.cpp"):
            copy_file(manifest_file(args.application_source, name), output, "recipes/application/" + name)
        link_plan(args, receipt, output)

        # This is an exact inventory of the target archives. A component-level
        # source binding does not resolve per-member license expressions.
        ledger = {}
        for archive in sorted((args.kit / "target").rglob("*.a")):
            name = archive.relative_to(args.kit).as_posix()
            source = manifest_file(args.kit, name)
            package_path = "link/kit/" + name
            copy_file(source, output, package_path)
            ledger[package_path] = {"archive_sha256": sha(source), "members": [
                {"name": member, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                for member, data in read_archive(source).items()]}
        require(ledger, "no target Qt static archives found")
        (output / "target_members.json").write_bytes(canonical(ledger))
        require(sha(kit_manifest) == kit_digest and fingerprint(args.kit)["tree_sha256"] == kit_format["tree_sha256"],
                "the Qt Quick kit changed during staging")

        files = {path.relative_to(output).as_posix(): {"sha256": sha(path), "bytes": path.stat().st_size}
                 for path in sorted(output.rglob("*")) if path.is_file()}
        manifest = {"format": "xos_qt_quick_release_materials_v1", "kit_manifest_sha256": kit_digest,
                    "source_provenance": provenance, "files": files}
        (output / "manifest.json").write_bytes(canonical(manifest))
        verified_manifest(output)
    except Exception:
        shutil.rmtree(output)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("kit", "qtdeclarative", "qtshadertools", "build-record", "application-build", "application-source", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--declarative-built-snapshot", action="store_true",
                        help="use the observed full patched source tree recorded with the installed archives")
    args = parser.parse_args()
    stage(args)
    print(sha(args.output / "manifest.json"))


if __name__ == "__main__":
    main()
