#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Cold-boot the relocated Mobius package through install, update and rollback."""

import argparse
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory

from mobius_glibc_guest import run_mobius
from mobius_glibc_xpk_guest import EXECUTABLES, PACKAGE_ID, PREFERENCES
from shell_launch_support import bind_system, sha

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from make_work_disk import create_fat32
from mobius_build_receipt import packaged_build_binding
from xos_app import application_sdk_check, sdk_notices
from xypm_format import canonical, load_json, require, verify_package
from xypm_image import Disk, query_image, transact

SESSION = ("session", "exec-driver /usr/bin/mobius-session.elf")
SHELLS = (("xsh", "exec-file /usr/bin/mobius.elf"), ("dash", "dash -c /usr/bin/mobius.elf"))
USER_DRAFT = "/usr/share/xos.mobius/user_draft.txt"


def check_package(package, target, profile, sdk, kit_digest, revision):
    result = verify_package(package, profile)
    manifest = result["manifest"]
    require(manifest["id"] == PACKAGE_ID and manifest["revision"] == revision, "wrong Mobius package revision")
    files = {item["path"]: item for item in manifest["files"]}
    require({name for name, item in files.items() if item["role"] == "executable"} == set(EXECUTABLES),
            "incorrect Mobius product entry points")
    payloads = {}
    for name, filename in EXECUTABLES.items():
        elf = target / filename
        receipt = elf.with_suffix(".receipt.json")
        linked = load_json(receipt)
        expected = {"elf_sha256": sha(elf), "widgets_kit_manifest_sha256": kit_digest}
        expected.update(packaged_build_binding(linked, sha(receipt)))
        require(expected["elf_sha256"] == files[name]["sha256"] == linked["elf_sha256"]
                and linked["widgets_kit_manifest_sha256"] == kit_digest
                and linked["sdk_manifest_sha256"] == profile["sdk_binding"]["sdk_manifest_sha256"],
                f"Mobius receiver link or Widgets kit binding differs: {name}")
        payloads[name] = expected
    notices = {f"sdk/{name}": path for path, name in sdk_notices(sdk, profile, "cpp")}
    qt = ROOT / "src/ports/qt6"
    notices.update({"QtBase-source-lock.json": qt / "source_lock.json",
                    "Aurora-artwork-provenance.json": qt / "aurora/assets/provenance.json"})
    gui = qt / "licenses/gui"
    notices.update({f"qt/gui/{path.relative_to(gui).as_posix()}": path
                    for path in sorted(gui.rglob("*")) if path.is_file()})
    for name, path in notices.items():
        dest = f"usr/share/licenses/{PACKAGE_ID}/{name}"
        require(dest in manifest["licenses"] and files[dest]["sha256"] == sha(path), f"wrong notice: {name}")
    return result, payloads


def inspect_disk(work, disk, profile, package, expected, user_data):
    manifest = package["manifest"]
    installed = query_image(disk, profile, "info", PACKAGE_ID)
    require(installed["manifest"] == manifest and installed["sha256"] == package["sha256"],
            "installed package database lost the exact revision or package digest")
    require(query_image(disk, profile, "verify-installed")["files"] == len(manifest["files"]),
            "installed inventory differs from the XPK")
    with Disk(disk, work, True) as mounted:
        receipt = load_json(mounted.export("/" + manifest["build_receipt"]["path"]))
        require(receipt["elfs"] == expected
                and receipt["sdk_manifest_sha256"] == profile["sdk_binding"]["sdk_manifest_sha256"],
                "installed receipt lost its SDK or application binding")
        if any("build_recipe_sha256" in item for item in expected.values()):
            require(receipt["revision"] == manifest["revision"], "installed receipt has the wrong product revision")
        for name, item in expected.items():
            require(sha(mounted.export("/" + name)) == item["elf_sha256"], f"installed ELF mismatch: {name}")
        return read_user_files(mounted, user_data)


def read_user_files(disk, user_data):
    files = {path: sha(disk.export(path)) for path in user_data}
    require(files == {path: sha(source) for path, source in user_data.items()}, "user data changed on the work disk")
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("system", "profile", "sdk-build", "widgets-kit-manifest", "reference", "replacement",
                   "reference-target", "replacement-target", "dash", "dash-receipt", "dash-sdk-manifest", "output"):
        parser.add_argument(f"--{option}", type=Path, required=True)
    parser.add_argument("--old-profile-package", type=Path, help="previous Mobius XPK for the profile boundary check")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True)
    report = {"status": "FAILED", "transactions": [], "phases": {}}
    try:
        profile = load_json(args.profile)
        binding = application_sdk_check(args.sdk_build, profile)
        system = bind_system(args.system)
        image = args.system / "xos-install.iso"
        kit_digest = sha(args.widgets_kit_manifest)
        kit = load_json(args.widgets_kit_manifest)
        require(kit["sdk_manifest_sha256"] == binding["sdk_manifest_sha256"]
                and kit["sdk_profile_file_sha256"] == sha(args.profile),
                "Widgets kit and glibc SDK do not match")
        before, before_elfs = check_package(args.reference, args.reference_target, profile,
                                            args.sdk_build, kit_digest, 0)
        after, after_elfs = check_package(args.replacement, args.replacement_target, profile,
                                          args.sdk_build, kit_digest, 1)
        require(before["sha256"] != after["sha256"]
                and before["manifest"]["build_receipt"]["sha256"] != after["manifest"]["build_receipt"]["sha256"],
                "upgrade must replace a managed package file")
        dash = load_json(args.dash_receipt)
        require(sha(args.dash) == dash["sha256"] and sha(args.dash_sdk_manifest) == dash["sdk_manifest_sha256"],
                "Dash ELF or SDK differs from its linked receipt")
        report.update(system_build_id=system["build_id"], system_manifest_sha256=sha(args.system / "manifest.json"),
                      iso_sha256=sha(image), sdk_binding=binding, profile_file_sha256=sha(args.profile),
                      widgets_kit_manifest_sha256=kit_digest, dash_elf_sha256=dash["sha256"],
                      dash_sdk_manifest_sha256=dash["sdk_manifest_sha256"], dash_receipt_sha256=sha(args.dash_receipt),
                      reference_sha256=before["sha256"], replacement_sha256=after["sha256"],
                      reference_payloads=before_elfs, replacement_payloads=after_elfs)
        with TemporaryDirectory(prefix="xos_mobius_unified_") as temporary:
            work = Path(temporary)
            source = work / "original.img"
            prefs, draft = work / "appearance.txt", work / "user_draft.txt"
            prefs.write_bytes(b"Existing Mobius appearance data.\n")
            draft.write_bytes(b"Mobius user document added after upgrade.\n")
            create_fat32(source, 512)
            with Disk(source, work) as mounted:
                for path in ("/usr", "/usr/bin", "/usr/share", "/usr/share/xos.mobius"):
                    mounted.command("mkdir", path)
                mounted.command("import", "/usr/bin/dash", args.dash)
                mounted.command("import", PREFERENCES, prefs)
            report["original_disk_sha256"] = sha(source)
            if args.old_profile_package:
                old = verify_package(args.old_profile_package)
                require(old["manifest"]["id"] == PACKAGE_ID, "legacy control needs a prior Mobius package")
                try:
                    verify_package(args.old_profile_package, profile)
                except ValueError as error:
                    require("target profile mismatch" in str(error), "unexpected old package failure")
                else:
                    raise AssertionError("old package passed the unified profile gate")
                report["previous_profile_package"] = {"sha256": old["sha256"],
                                                      "profile_id": old["manifest"]["target_profile"],
                                                      "unified_profile_rejected": True}

            def guest_phase(name, disk, package, payloads, user_data, launchers):
                data = {"user_data": inspect_disk(work, disk, profile, package, payloads, user_data)}
                phase = output / name
                phase.mkdir()
                run_mobius(image, disk, phase, data, launchers=launchers)
                require(data["user_data"] == inspect_disk(work, disk, profile, package, payloads, user_data),
                        "guest changed a managed file or user data")
                uart = phase / "mobius_serial.log"
                serial = uart.read_bytes()
                dash_run = serial.split(b"dash -c /usr/bin/mobius.elf", 1)[1]
                require(re.search(rb"\[loader\] started pid=\d+ file=/usr/bin/dash", dash_run) is not None
                        and b"DESKTOP_READY" in dash_run, "Dash desktop route did not run")
                data["serial_sha256"] = sha(uart)
                report["phases"][name] = data

            installed, upgraded = work / "installed.img", work / "upgraded.img"
            report["transactions"].append(transact(source, installed, profile, "install", package=args.reference,
                                                   expected_sha256=before["sha256"]))
            guest_phase("installed", installed, before, before_elfs, {PREFERENCES: prefs}, SHELLS)
            report["transactions"].append(transact(installed, upgraded, profile, "upgrade", package=args.replacement,
                                                   expected_sha256=after["sha256"]))
            with Disk(upgraded, work) as mounted:
                mounted.command("import", USER_DRAFT, draft)
            user_data = {PREFERENCES: prefs, USER_DRAFT: draft}
            guest_phase("upgraded", upgraded, after, after_elfs, user_data, SHELLS + (SESSION,))
            removed, restored = work / "removed.img", work / "restored.img"
            report["transactions"].append(transact(upgraded, removed, profile, "remove", package_id=PACKAGE_ID))
            require(query_image(removed, profile, "verify-installed")["files"] == 0, "removed package left managed files")
            with Disk(removed, work, True) as mounted:
                report["removed_user_data"] = read_user_files(mounted, user_data)
            report["transactions"].append(transact(removed, restored, profile, "install", package=args.reference,
                                                   expected_sha256=before["sha256"]))
            guest_phase("restored", restored, before, before_elfs, user_data, SHELLS)
            require(sha(source) == report["original_disk_sha256"], "package lifecycle mutated original disk")
        report["status"] = "PASSED"
    finally:
        (output / "report.json").write_bytes(canonical(report))
    print(report["status"])


if __name__ == "__main__":
    main()
