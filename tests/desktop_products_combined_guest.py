#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Boot Mobius, ClarkE, and the external Qt Quick example from one XOS work disk."""

import argparse
from pathlib import Path
import subprocess
import tempfile

from boot_smoke import Guest
from clarke_glibc_xpk_guest import boot_browser
from graphics_guest import start_graphics, stop_graphics, wait_for_scanout
from make_work_disk import create_fat32
from mobius_glibc_guest import run_mobius
from process_smoke import resources
from task_smoke import pump, send_bytes
from xos_app import application_sdk_check
from xypm_format import canonical, inspect_elf, load_json, require, sha_file, verify_package
from xypm_image import Disk, query_image, transact

QUICK_PATH = "/bin/quick-example.elf"
USER_PATH = "/web/user.html"


def quick_pixels(frame):
    if frame.size != (800, 600):
        return False
    window = frame.crop((32, 40, 292, 200))
    colors = {color: count for count, color in window.getcolors(260 * 160)}
    return colors.get((24, 60, 56), 0) > 38000 and colors.get((255, 255, 255), 0) > 100


def run_quick(image, disk, output):
    output.mkdir()
    guest = Guest(image, "quick", work_disk=disk, log_dir=output)
    try:
        guest.expect(b"xos64> ", timeout=60)
        send_bytes(guest, b"run\r")
        guest.expect_supervisor(trace=True, timeout=60)
        pump(guest, 1.5)
        baseline = resources(guest)
        graphics = start_graphics(guest)
        active = resources(guest)
        begin = len(guest.output)
        send_bytes(guest, f"exec-file {QUICK_PATH}\r".encode())
        guest.expect(b"[qpa-frame]", start=begin, timeout=90)
        scanout = output / "quick.ppm"
        frame = wait_for_scanout(guest, scanout, quick_pixels)
        frame.save(output / "quick.png")
        guest.expect(b"kind=exited code=0", start=begin, timeout=30)
        guest.expect_supervisor(start=begin)
        guest.expect(b"input-thread-joined", start=begin)
        require(resources(guest) == active, "Qt Quick example resources did not return")
        stop_graphics(guest, *graphics)
        require(resources(guest) == baseline, "Qt Quick graphics services did not return resources")
        return {"scanout_sha256": sha_file(scanout), "baseline": baseline, "with_graphics": active}
    finally:
        guest.close()
        (output / "serial.log").write_bytes(guest.output)


def main():
    if not __debug__:
        raise SystemExit("guest helpers require Python assertions")
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("system", "sdk", "profile", "mobius", "clarke", "quick", "quick-receipt", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True)
    report = {"status": "failed"}
    try:
        image = args.system.resolve() / "xos-install.iso"
        manifest = args.system / "manifest.json"
        system = load_json(manifest)
        profile = load_json(args.profile)
        binding = application_sdk_check(args.sdk, profile)
        quick = load_json(args.quick_receipt)
        quick_sha = sha_file(args.quick)
        require(profile.get("runtime_family") == "glibc", "combined test requires glibc")
        require(quick_sha == quick["elf_sha256"] and
                quick["sdk_manifest_sha256"] == binding["sdk_manifest_sha256"], "Qt Quick receipt mismatch")
        image_sha = sha_file(image)
        require(image_sha == system["artifacts"]["xos-install.iso"]["sha256"], "system ISO mismatch")
        inspect_elf(args.quick)
        packages = (("xos.mobius", args.mobius), ("xos.clarke", args.clarke))
        manifests = {}
        for product, archive in packages:
            package = verify_package(archive, profile)["manifest"]
            require(package["id"] == product, f"unexpected package for {product}")
            manifests[product] = package
        report.update(system_build=system["build_id"], system_source_sha256=system["source_sha256"],
                      system_manifest_sha256=sha_file(manifest),
                      iso_sha256=image_sha, sdk=binding, profile_sha256=sha_file(args.profile),
                      packages={product: sha_file(archive) for product, archive in packages},
                      quick_sha256=quick_sha, quick_receipt_sha256=sha_file(args.quick_receipt))
        with tempfile.TemporaryDirectory(prefix="xos_desktop_products_") as temporary:
            work = Path(temporary)
            original, mobius, both, clarke = (work / f"{name}.img" for name in
                                                ("original", "mobius", "both", "clarke"))
            user = work / "user.html"
            user.write_text("<html><p>My XOS page</p></html>\n", encoding="utf-8")
            create_fat32(original, 512)
            with Disk(original, work) as disk:
                disk.command("mkdir", "/bin")
                disk.command("mkdir", "/web")
                disk.command("import", QUICK_PATH, args.quick.resolve())
                disk.command("import", USER_PATH, user)
            source_sha = sha_file(original)
            report["transactions"] = [transact(original, mobius, profile, "install", package=args.mobius),
                                      transact(mobius, both, profile, "install", package=args.clarke)]
            installed = query_image(both, profile)["packages"]
            require({item["id"] for item in installed} == manifests.keys(), "expected both products")
            require(query_image(both, profile, "verify-installed")["files"] ==
                    sum(len(item["files"]) for item in manifests.values()), "incorrect installed file count")
            with Disk(both, work, True) as disk:
                require(disk.info("/web/start.html") is None, "ClarkE needs to use its packaged start page")

            (output / "mobius").mkdir()
            report["mobius"] = {}
            run_mobius(image, both, output / "mobius", report["mobius"])
            report["clarke"] = boot_browser(image, both, output / "clarke", "/usr/bin/clarke.elf",
                                             "/web/start.html", css_loaded=True)
            report["quick"] = run_quick(image, both, output / "quick")

            report["transactions"].append(transact(both, clarke, profile, "remove", package_id="xos.mobius"))
            require(query_image(clarke, profile, "info", package_id="xos.clarke")["manifest"] ==
                    manifests["xos.clarke"], "ClarkE receipt changed during the Mobius removal")
            require(query_image(clarke, profile, "verify-installed")["files"] ==
                    len(manifests["xos.clarke"]["files"]), "ClarkE installed files changed")
            with Disk(clarke, work, True) as disk:
                require(disk.info("/usr/bin/mobius.elf") is None and
                        disk.info("/usr/bin/mobius-session.elf") is None, "Mobius launchers survived removal")
                require(sha_file(disk.export(USER_PATH)) == sha_file(user) and
                        sha_file(disk.export(QUICK_PATH)) == quick_sha, "unmanaged user files changed")
            report["clarke_after_mobius_removal"] = boot_browser(
                image, clarke, output / "clarke-after-mobius-removal", "/usr/bin/clarke.elf",
                "/web/start.html", css_loaded=True)
            require(sha_file(original) == source_sha, "source disk changed")
            report["status"] = "passed"
    finally:
        (output / "report.json").write_bytes(canonical(report))


if __name__ == "__main__":
    main()
