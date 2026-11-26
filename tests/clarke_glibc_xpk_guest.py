#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Qualify the private ClarkE glibc XPK and preservation of an older browser work disk."""

import argparse
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from boot_smoke import Guest
from desktop_product_packages import press
from graphics_guest import start_graphics, stop_graphics, wait_for_scanout
from make_work_disk import create_fat32
from process_smoke import resources
from task_smoke import pump, send_bytes
from xos_app import application_sdk_check, sdk_notices
from xypm_format import DEFAULT_PROFILE, canonical, inspect_elf, load_json, require, sha_file, verify_package
from xypm_image import Disk, query_image, transact

PRODUCT = "xos.clarke"
EXECUTABLE = "usr/bin/clarke.elf"
LEGACY = "/bin/browser.elf"
PAGE = "/web/user.html"
BUILT_INS = {f"usr/share/{PRODUCT}/web/{name}" for name in
             ("start.html", "reading.html", "garden.html", "garden.bmp", "theme.css")}


def boot_browser(image, disk, destination, invocation, page, css_loaded=False):
    destination.mkdir()
    guest = Guest(image, "clarke", work_disk=disk, iso=True, log_dir=destination)
    try:
        guest.expect(b"xos64> ", timeout=60)
        send_bytes(guest, b"run\r")
        guest.expect_supervisor(trace=True, timeout=60)
        pump(guest, 1.5)
        baseline = resources(guest)
        graphics = start_graphics(guest)
        active = resources(guest)
        begin = len(guest.output)
        send_bytes(guest, f"exec-file {invocation}\r".encode())
        guest.expect(f"BROWSER_LOADED path={page}".encode(), start=begin, timeout=90)
        if css_loaded:
            guest.expect(b"BROWSER_CSS_LOADED path=/web/theme.css", start=begin, timeout=45)
        guest.expect(b"BROWSER_READY engine=litehtml-0.9 local_only=1", start=begin, timeout=45)
        frame = destination / "page.ppm"
        picture = wait_for_scanout(guest, frame, lambda im: im.size == (800, 600) and
                                   any(count > 50000 and color == (244, 247, 252)
                                       for count, color in im.getcolors(800 * 600)))
        picture.save(destination / "page.png")
        press(guest, "esc")
        guest.expect(b"kind=exited code=0", start=begin, timeout=45)
        guest.expect_supervisor(start=begin)
        require(resources(guest) == active, "ClarkE guest resources did not return")
        stop_graphics(guest, *graphics)
        require(resources(guest) == baseline, "graphics guest resources did not return")
        return {"scanout_sha256": sha_file(frame), "baseline": baseline, "with_graphics": active}
    finally:
        guest.close()
        (destination / "serial.log").write_bytes(guest.output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("system", "elf", "sdk-build", "profile", "package", "update",
                 "legacy", "legacy-receipt", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True)
    profile = load_json(args.profile)
    require(profile.get("runtime_family") == "glibc", "ClarkE package check requires a glibc profile")
    binding = application_sdk_check(args.sdk_build, profile)
    system_manifest = args.system / "manifest.json"
    system = load_json(system_manifest)
    image = args.system / "xos-install.iso"
    require(sha_file(image) == system["artifacts"]["xos-install.iso"]["sha256"], "system ISO mismatch")
    elf_digest = sha_file(args.elf)
    require(elf_digest == load_json(args.elf.with_suffix(".receipt.json"))["elf_sha256"], "ClarkE receipt mismatch")
    legacy_digest = sha_file(args.legacy)
    require(legacy_digest == load_json(args.legacy_receipt)["elf_sha256"], "legacy ClarkE receipt mismatch")
    inspect_elf(args.legacy)
    packages = [verify_package(path, profile) for path in (args.package, args.update)]
    initial, update = [package["manifest"] for package in packages]
    require(initial["revision"] < update["revision"], "ClarkE package revision must increase")
    for manifest in (initial, update):
        files = {part["path"]: part for part in manifest["files"]}
        require(manifest["id"] == PRODUCT and files[EXECUTABLE]["sha256"] == elf_digest,
                "unexpected ClarkE package identity or executable")
        require(BUILT_INS <= files.keys(), "ClarkE packaged pages are missing")
        for notice, name in sdk_notices(args.sdk_build, profile, "cpp"):
            path = f"usr/share/licenses/{PRODUCT}/sdk/{name}"
            require(path in manifest["licenses"] and files[path]["sha256"] == sha_file(notice),
                    f"SDK notice absent or changed: {name}")

    report = {"status": "failed", "system_build_id": system["build_id"], "image_sha256": sha_file(image),
              "system_manifest_sha256": sha_file(system_manifest), "sdk_binding": binding,
              "elf_sha256": elf_digest, "legacy_sha256": legacy_digest,
              "packages_sha256": [entry["sha256"] for entry in packages], "transactions": [], "checks": []}
    try:
        with tempfile.TemporaryDirectory(prefix="xos_clarke_package_") as temporary:
            work = Path(temporary)
            source, installed, upgraded, removed = [work / f"{name}.img" for name in
                                                     ("old", "installed", "upgraded", "removed")]
            create_fat32(source, 512)
            local_page = work / "user.html"
            local_page.write_text("<html><head><title>My Work Disk</title><style>body { "
                                  "background-color: #f4f7fc; }</style></head>"
                                  "<body><h1>My preserved local page</h1></body></html>", encoding="utf-8")
            with Disk(source, work) as disk:
                for path in ("/bin", "/usr", "/usr/bin", "/web"):
                    disk.command("mkdir", path)
                disk.command("import", LEGACY, args.legacy)
                disk.command("import", PAGE, local_page)
            original = sha_file(source)
            wrong = work / "wrong-profile.img"
            try:
                transact(source, wrong, load_json(DEFAULT_PROFILE), "install", package=args.package)
            except ValueError as error:
                require("target profile mismatch" in str(error) and not wrong.exists(),
                        "newlib rejected the glibc package for an unexpected reason")
            else:
                raise AssertionError("newlib profile admitted the glibc ClarkE package")
            report["checks"].append("glibc_package_rejected_by_frozen_newlib_profile")

            report["transactions"].append(transact(source, installed, profile, "install", package=args.package))
            report["transactions"].append(transact(installed, upgraded, profile, "upgrade", package=args.update))
            require(query_image(upgraded, profile, "info", package_id=PRODUCT)["manifest"] == update,
                    "incorrect installed ClarkE revision")
            require(query_image(upgraded, profile, "verify-installed")["files"] == len(update["files"]),
                    "incorrect installed ClarkE inventory")
            with Disk(upgraded, work, True) as disk:
                require(disk.info("/web/start.html") is None and disk.info("/web/theme.css") is None,
                        "browser page test needs the installed files as its only start page")
            report["installed"] = boot_browser(image, upgraded, output / "installed",
                                               "/" + EXECUTABLE, "/web/start.html", css_loaded=True)
            report["checks"].append("installed_glibc_clarke_page_and_stylesheet_scanout")

            report["transactions"].append(transact(upgraded, removed, profile, "remove", package_id=PRODUCT))
            require(query_image(removed, profile, "verify-installed")["files"] == 0, "managed files survived removal")
            with Disk(removed, work, True) as disk:
                require(all(disk.info("/" + part["path"]) is None for part in update["files"]),
                        "managed paths survived removal")
                require(sha_file(disk.export(LEGACY)) == legacy_digest, "legacy ELF changed")
                require(sha_file(disk.export(PAGE)) == sha_file(local_page), "user page changed")
            report["legacy"] = boot_browser(image, removed, output / "removed", f"{LEGACY} {PAGE}", PAGE)
            require(sha_file(source) == original, "original work disk changed")
            report["checks"].append("legacy_browser_reads_preserved_user_page_after_removal")
            report["status"] = "passed"
    finally:
        (output / "report.json").write_bytes(canonical(report))


if __name__ == "__main__":
    main()
