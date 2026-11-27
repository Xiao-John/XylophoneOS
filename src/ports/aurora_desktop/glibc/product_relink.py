#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Capture Mobius link inputs and reproduce its two static executables offline."""

import argparse
from pathlib import Path, PurePosixPath
import shlex
import shutil
import subprocess
from tempfile import TemporaryDirectory

from widgets_kit import QT, ROOT, TARGET_RECEIPT, verify_kit
from release_materials import copy_file
from relink import json_read, link_flags, manifest_file, require, sha, verify_static_elf
from xos_app import sdk_notices
from xypm_format import canonical
from xypm_sdk_profile import metadata_snapshot, verify_profile

programs = ("mobius.elf", "mobius_session.elf")
product_link_flags = link_flags | {"-Wl,--require-defined=xos_file_session_exchange"}


def link_plan(build, name, sdk, kit, output):
    commands = subprocess.check_output(["ninja", "-C", build, "-t", "commands", name], text=True)
    tokens = shlex.split(commands.splitlines()[-1])
    require(tokens[:2] == [":", "&&"] and tokens[-2:] == ["&&", ":"]
            and PurePosixPath(tokens[2]).name == "x86_64-elf-g++"
            and tokens[3] == "--sysroot=" + str(sdk),
            "Unexpected Mobius static link command")
    options = tokens[tokens.index("-static"):-2]
    index = options.index("-o")
    require(options[index + 1] == name, "Mobius link command names another executable")
    del options[index:index + 2]
    plan = []
    for option in options:
        if option in product_link_flags:
            plan.append(option)
            continue
        path = PurePosixPath(option)
        require(path.suffix in (".a", ".o", ".ld"), f"Unexpected Mobius link input: {path.name}")
        if not path.is_absolute():
            root, relative, prefix = build, path, "link/objects"
        elif path.is_relative_to(sdk):
            root, relative, prefix = sdk, path.relative_to(sdk), "link/sdk"
        else:
            root, relative, prefix = kit / "target", path.relative_to(kit / "target"), "link/qt"
        destination = f"{prefix}/{relative.as_posix()}"
        copy_file(manifest_file(root, relative.as_posix()), output, destination)
        plan.append({"file": destination})
    return plan


def stage(args):
    build, kit, sdk = (path.resolve(strict=True) for path in (args.build, args.widgets_kit, args.sdk_build))
    output = args.output.absolute()
    require(not output.is_symlink() and not output.exists()
            and not any(output.resolve().is_relative_to(path) for path in (build, kit, sdk, ROOT / "src")),
            "Use a fresh materials directory outside the build inputs")
    profile = json_read(args.sdk_profile)
    binding = verify_profile(profile, "glibc", sdk)
    sdk_digest = profile["sdk_binding"]["sdk_manifest_sha256"]
    profile_digest = sha(args.sdk_profile)
    kit_digest = verify_kit(kit, args.widgets_kit_sha256, sdk_digest, profile_digest,
                            profile_id=binding["profile_id"])
    kit_manifest = json_read(kit / "manifest.json")
    require(sha(args.qtbase) == kit_manifest["qtbase_archive_sha256"], "QtBase source differs from the Widgets kit")
    sdk_manifest, _ = metadata_snapshot(sdk / "manifest.json", sdk_digest)
    tools = {name: sdk_manifest["tools"][f"x86_64-elf-{name}"]["sha256"] for name in ("g++", "ld", "as")}
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=f".{output.name}-", dir=output.parent) as temporary:
        staged = Path(temporary) / output.name
        links = {}
        for name in programs:
            elf = manifest_file(build, name)
            receipt_file = elf.with_suffix(".receipt.json")
            receipt_digest = sha(receipt_file)
            receipt = json_read(receipt_file)
            require(receipt["elf_sha256"] == sha(elf) and receipt["sdk_manifest_sha256"] == sdk_digest
                    and receipt["widgets_kit_manifest_sha256"] == kit_digest
                    and all(receipt["target_tools"][name] == digest for name, digest in tools.items()),
                    f"Wrong Mobius build, SDK, or kit receipt: {name}")
            for filename, digest in receipt["inputs"].items():
                path = Path(filename)
                require(sha(path) == digest, f"Mobius build input changed: {path.name}")
                if path.is_relative_to(ROOT / "src"):
                    copy_file(path, staged, f"sources/xos/{path.relative_to(ROOT).as_posix()}")
            links[name] = {"elf_sha256": receipt["elf_sha256"], "build_receipt_sha256": receipt_digest,
                           "plan": link_plan(build, name, sdk / "sysroot", kit, staged)}
            require(sha(elf) == receipt["elf_sha256"] and sha(receipt_file) == receipt_digest,
                    f"Mobius executable or receipt changed after staging: {name}")
        copy_file(args.qtbase, staged, "sources/qtbase.tar.xz")
        copy_file(kit / "manifest.json", staged, "notices/widgets_kit.json")
        if "target_receipt_sha256" in kit_manifest:
            copy_file(kit / TARGET_RECEIPT, staged, "notices/widgets_target_receipt.json")
            require(sha(staged / "notices/widgets_target_receipt.json") == kit_manifest["target_receipt_sha256"],
                    "Widgets target receipt changed during staging")
        copy_file(args.sdk_profile, staged, "notices/sdk_profile.json")
        for path, name in sdk_notices(sdk, profile, "cpp"):
            copy_file(path, staged, f"notices/sdk/{name}")
        shutil.copytree(kit / "notices", staged / "notices/qt")
        for path in (QT / "prepare_source.py", QT / "prepare_gui_source.py", QT / "prepare_widgets_source.py",
                     QT / "glibc/glibc_qtcore.patch", QT / "quick/glibc_qtbase_platform.patch",
                     QT / "aurora/assets/provenance.json", QT / "aurora/shell/artwork/Curvive.png",
                     ROOT / "LICENSE", ROOT / "NOTICE",
                     *(p for p in (QT / "patches").rglob("*") if p.is_file())):
            copy_file(path, staged, f"sources/xos/{path.relative_to(ROOT).as_posix()}")
        require(sha(staged / "sources/qtbase.tar.xz") == kit_manifest["qtbase_archive_sha256"]
                and verify_kit(kit, kit_digest, sdk_digest, profile_digest,
                               profile_id=binding["profile_id"]) == kit_digest,
                "Qt source archive or Widgets kit changed during staging")
        files = {item.relative_to(staged).as_posix(): sha(item)
                 for item in sorted(staged.rglob("*")) if item.is_file()}
        manifest = {"format_version": 1, "kind": "mobius_static_relink", "files": files, "programs": links,
                    "widgets_kit_manifest_sha256": kit_digest, "sdk_manifest_sha256": sdk_digest,
                    "sdk_profile_file_sha256": profile_digest, "target_tools": tools}
        (staged / "manifest.json").write_bytes(canonical(manifest))
        staged.rename(output)
    print(sha(output / "manifest.json"))


def load_replacement(directory, expected, materials, materials_digest):
    directory = directory.resolve(strict=True)
    replacement, digest = metadata_snapshot(manifest_file(directory, "manifest.json"), expected)
    require(replacement.get("format_version") == 1 and replacement.get("kind") == "mobius_qt_replacement"
            and replacement.get("materials_manifest_sha256") == materials_digest,
            "Qt replacement belongs to different Mobius link materials")
    filename = replacement["library"]
    library = PurePosixPath(filename)
    require(library.parent == PurePosixPath("link/qt/lib") and library.as_posix() == filename
            and library.name.startswith("libQt6") and library.suffix == ".a"
            and filename in materials["files"], "Replacement must select one material Qt archive")
    original = materials["files"][filename]
    require(replacement["original_archive_sha256"] == original
            and replacement["archive_sha256"] != original, "Qt replacement must change the bound original archive")
    users = {name for name, record in materials["programs"].items() if {"file": filename} in record["plan"]}
    require(users, "No Mobius link plan uses the selected Qt archive")
    return replacement, digest, manifest_file(directory, library.name), users


def relink(args):
    materials = args.materials.resolve(strict=True)
    manifest, digest = metadata_snapshot(manifest_file(materials, "manifest.json"), args.sha256)
    require(manifest["format_version"] == 1 and manifest["kind"] == "mobius_static_relink"
            and set(manifest["programs"]) == set(programs), "Expected the two Mobius product link plans")
    files = manifest["files"]
    paths = list(materials.rglob("*"))
    require(all(not path.is_symlink() and (path.is_file() or path.is_dir()) for path in paths),
            "Mobius materials require ordinary files and directories")
    actual = {path.relative_to(materials).as_posix() for path in paths if path.is_file()}
    require(actual == files.keys() | {"manifest.json"}, "Unexpected Mobius materials inventory")
    for name, expected in files.items():
        require(sha(manifest_file(materials, name)) == expected, f"Changed Mobius materials file: {name}")
    tools = {}
    require(set(manifest["target_tools"]) == {"g++", "as", "ld"}, "Incomplete target tool binding")
    for name, expected in manifest["target_tools"].items():
        executable = shutil.which(f"x86_64-elf-{name}")
        require(executable is not None and sha(Path(executable)) == expected, f"Changed target tool: {name}")
        tools[name] = Path(executable).resolve(strict=True)
    require((args.replacement is None) == (args.replacement_sha256 is None),
            "Provide the Qt replacement directory and its manifest SHA-256 together")
    replacement = None
    if args.replacement is not None:
        replacement = load_replacement(args.replacement, args.replacement_sha256, manifest, digest)
    output = args.output.absolute()
    inputs = (materials, args.replacement.resolve()) if replacement is not None else (materials,)
    require(not output.is_symlink() and not output.exists()
            and not any(output.resolve().is_relative_to(path) for path in inputs),
            "Use a fresh relink output directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=f".{output.name}-", dir=output.parent) as temporary:
        stage_dir = Path(temporary)
        staged, aliases = stage_dir / "result", stage_dir / "tools"
        staged.mkdir()
        aliases.mkdir()
        for name in ("as", "ld"):
            (aliases / name).symlink_to(tools[name])
        library = None
        if replacement is not None:
            metadata, replacement_digest, archive, users = replacement
            library = metadata["library"]
            archive_copy = stage_dir / archive.name
            shutil.copyfile(archive, archive_copy)
            with archive_copy.open("rb") as stream:
                require(stream.read(8) == b"!<arch>\n", "Qt replacement must be a regular static archive")
            require(sha(archive_copy) == metadata["archive_sha256"], "Qt replacement archive digest mismatch")
        seen = {}
        changed = []
        for program, record in manifest["programs"].items():
            arguments = []
            for item in record["plan"]:
                if isinstance(item, str):
                    require(item in product_link_flags, "Unexpected flag in the Mobius link plan")
                    arguments.append(item)
                else:
                    require(item.keys() == {"file"} and item["file"] in files, "Unbound Mobius link input")
                    selected = archive_copy if item["file"] == library else manifest_file(materials, item["file"])
                    arguments.append(str(selected))
            elf = staged / program
            subprocess.run([tools["g++"], f"--sysroot={materials / 'link/sdk'}", f"-B{aliases}/",
                            *arguments, "-o", elf], check=True)
            verify_static_elf(elf)
            seen[program] = sha(elf)
            if seen[program] != record["elf_sha256"]:
                require(replacement is not None and program in users, f"Relink differs from the original {program}")
                changed.append(program)
        receipt = {
            "status": "byte_identical_mobius_relink", "materials_manifest_sha256": digest, "elfs": seen,
        }
        if replacement is not None:
            require(changed, "Qt replacement did not change either product ELF")
            receipt.update(status="mobius_qt_replacement_linked", changed_programs=sorted(changed),
                           replacement_manifest_sha256=replacement_digest, library=library,
                           original_archive_sha256=metadata["original_archive_sha256"],
                           replacement_archive_sha256=metadata["archive_sha256"])
        (staged / "receipt.json").write_bytes(canonical(receipt))
        staged.rename(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    producer = actions.add_parser("stage")
    for option in ("build", "widgets-kit", "sdk-build", "sdk-profile", "qtbase", "output"):
        producer.add_argument(f"--{option}", type=Path, required=True)
    producer.add_argument("--widgets-kit-sha256", required=True)
    receiver = actions.add_parser("relink")
    for option in ("materials", "output"):
        receiver.add_argument(f"--{option}", type=Path, required=True)
    receiver.add_argument("--sha256", required=True)
    receiver.add_argument("--replacement", type=Path, help="directory with one Qt archive and its manifest")
    receiver.add_argument("--replacement-sha256", help="expected manifest SHA-256 of the Qt replacement")
    args = parser.parse_args()
    (stage if args.action == "stage" else relink)(args)


if __name__ == "__main__":
    main()
