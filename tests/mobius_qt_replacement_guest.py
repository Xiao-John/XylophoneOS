#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Observe the rebuilt Qt path painter in a Mobius replacement on an ordinary XOS ISO."""

import argparse
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from mobius_glibc_guest import run_mobius
from shell_launch_support import bind_system, sha

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from make_work_disk import create_fat32
from xypm_format import canonical, load_json, require
from xypm_image import Disk

TRACE = b"QT_V2_REPLACEMENT_PAINTER_PATH"
DESKTOP = "mobius.elf"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("system", "baseline", "replacement", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--system-source", type=Path, default=ROOT)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True)
    system = bind_system(args.system, args.system_source)
    image = args.system / "xos-install.iso"
    normal = load_json(args.baseline / "receipt.json")
    modified = load_json(args.replacement / "receipt.json")
    require(normal["status"] == "byte_identical_mobius_relink"
            and modified["status"] == "mobius_qt_replacement_linked"
            and modified["materials_manifest_sha256"] == normal["materials_manifest_sha256"]
            and modified["changed_programs"] == [DESKTOP]
            and modified["elfs"][DESKTOP] != normal["elfs"][DESKTOP]
            and modified["elfs"]["mobius_session.elf"] == normal["elfs"]["mobius_session.elf"],
            "Expected matching original and Qt-only replacement relinks")
    report = {"status": "failed", "system_build_id": system["build_id"], "iso_sha256": sha(image),
              "system_manifest_sha256": sha(args.system / "manifest.json"), "cases": {}}
    try:
        with TemporaryDirectory(prefix="mobius_qt_replacement_") as folder:
            work = Path(folder)
            for name, target, receipt, want_trace in (
                ("baseline", args.baseline, normal, False), ("replacement", args.replacement, modified, True),
            ):
                elf = target / DESKTOP
                require(sha(elf) == receipt["elfs"][DESKTOP], "Desktop ELF differs from its relink receipt")
                disk = work / f"{name}.img"
                create_fat32(disk, 512)
                with Disk(disk, work) as mounted:
                    mounted.command("mkdir", "/usr")
                    mounted.command("mkdir", "/usr/bin")
                    mounted.command("import", f"/usr/bin/{DESKTOP}", elf)
                    require(sha(mounted.export(f"/usr/bin/{DESKTOP}")) == receipt["elfs"][DESKTOP],
                            "Test disk did not receive the bound desktop ELF")
                case = output / name
                case.mkdir()
                data = {"elf_sha256": sha(elf), "relink_receipt_sha256": sha(target / "receipt.json")}
                report["cases"][name] = data
                run_mobius(image, disk, case, data, launchers=(("xsh", "exec-file /usr/bin/mobius.elf"),))
                serial = case / "mobius_serial.log"
                data["serial_sha256"] = sha(serial)
                data["painter_path_trace_count"] = serial.read_bytes().count(TRACE)
                require(bool(data["painter_path_trace_count"]) == want_trace, "Qt painter path marker did not match the relink mode")
        report["status"] = "passed"
    finally:
        (output / "report.json").write_bytes(canonical(report))


if __name__ == "__main__":
    main()
