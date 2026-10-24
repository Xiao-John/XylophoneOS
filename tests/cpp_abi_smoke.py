# SPDX-License-Identifier: Apache-2.0
"""Build C++ ABI probes and optionally execute them in the XOS guest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts" / "build_cpp_abi_probe.py"
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]


def feature_markers(name: str) -> tuple[list[bytes], list[bytes], list[bytes]]:
    required: dict[str, tuple[list[bytes], list[bytes], list[bytes]]] = {
        "string_vector": ([b"[cpp_abi] string_vector=ok"], [b"=fail"], []),
        "exceptions": ([b"[cpp_abi] exception_unwind=ok"], [b"=fail", b"exception_unwind=missing"], []),
        "rtti": ([b"[cpp_abi] rtti=ok"], [b"=fail"], []),
        "local_static": ([b"[cpp_abi] local_static=ok"], [b"=fail"], []),
        "tls_destructors": ([b"[cpp_abi] tls_before_normal_exit", b"[cpp_abi] tls_dtor_normal_exit"],
                             [b"=fail"], [b"[cpp_abi] tls_before_normal_exit", b"[cpp_abi] tls_dtor_normal_exit"]),
        "multi_tu": ([b"[cpp_abi] tu_a_ctor", b"[cpp_abi] tu_b_ctor", b"[cpp_abi] multi_tu_init=ok",
                      b"[cpp_abi] tu_b_dtor_order=ok", b"[cpp_abi] tu_a_dtor"],
                     [b"=fail"], [b"[cpp_abi] tu_a_ctor", b"[cpp_abi] tu_b_ctor",
                                  b"[cpp_abi] tu_b_dtor_order=ok", b"[cpp_abi] tu_a_dtor"]),
    }
    return required[name]


def check_guest_feature(guest: Any, name: str, elf: Path, baseline: tuple[int, ...],
                       resources: Any, command: Any) -> dict[str, Any]:
    marker, forbidden, ordered = feature_markers(name)
    output = command(guest, f"exec-file /bin/{elf.name}", b"kind=exited code=", timeout=60)
    if b"kind=exited code=0" not in output:
        raise AssertionError(f"{name}: guest exited nonzero: {output[-1600:]!r}")
    for expected in marker:
        if expected not in output:
            raise AssertionError(f"{name}: missing guest marker {expected!r}: {output[-1600:]!r}")
    for rejected in forbidden:
        if rejected in output:
            raise AssertionError(f"{name}: failure marker {rejected!r}: {output[-1600:]!r}")
    if ordered:
        positions = [output.find(value) for value in ordered]
        if any(position < 0 for position in positions) or positions != sorted(positions):
            raise AssertionError(f"{name}: lifecycle markers out of order: {positions}")
    if resources(guest) != baseline:
        raise AssertionError(f"{name}: task/page/completion resources differ from baseline")
    return {"status": "passed", "guest_exit_code": 0,
            "markers": [value.decode("ascii") for value in marker],
            "ordered_markers": [value.decode("ascii") for value in ordered],
            "output_sha256": hashlib.sha256(output).hexdigest(),
            "guest_output_bytes": len(output)}


def symlink_component(path: Path) -> Path | None:
    absolute = Path(os.path.abspath(path.expanduser()))
    return next((component for component in reversed((absolute, *absolute.parents))
                 if component.is_symlink()), None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", required=True, type=Path)
    parser.add_argument("--runtime-prefix", required=True, type=Path)
    parser.add_argument("--runtime-manifest", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--features", default="string_vector,exceptions,rtti,local_static,tls_destructors,multi_tu")
    parser.add_argument("--run-guest", action="store_true", help="run built probes on a temporary FAT32 disk in XOS")
    args = parser.parse_args()
    linked = symlink_component(args.output_root)
    if linked is not None:
        print(f"NOT_READY: --output-root contains a symlink component: {linked}", file=sys.stderr)
        return 2
    output_root = args.output_root.expanduser().resolve()
    builder_started_ns = time.time_ns()
    command = [sys.executable, str(BUILDER), "--sdk", str(args.sdk),
               "--runtime-prefix", str(args.runtime_prefix),
               "--runtime-manifest", str(args.runtime_manifest),
               "--output-root", str(args.output_root), "--features", args.features]
    try:
        result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    except OSError as exc:
        result = None
        builder_returncode = 1
        builder_stdout = ""
        builder_stderr = str(exc)
    else:
        builder_returncode = result.returncode
        builder_stdout = result.stdout
        builder_stderr = result.stderr

    build_report_path = output_root / "cpp_abi_build_report.json"
    report: dict[str, Any] = {
        "schema_version": 1,
        "suite_scope": "early target C++ ABI probe; not the E08-5 native compiler gate",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "not_ready" if builder_returncode == 2 else "failed" if builder_returncode != 0 else "built_not_run",
        "guest_execution": "not_run",
        "builder_command": command,
        "builder_returncode": builder_returncode,
        "builder_stdout": builder_stdout,
        "builder_stderr": builder_stderr,
        "build_report": str(build_report_path),
    }
    try:
        build_report = json.loads(build_report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        build_report = None
        if builder_returncode == 0:
            report["status"] = "failed"
            report["report_error"] = f"builder succeeded without a readable report: {exc}"
    if (isinstance(build_report, dict) and builder_returncode == 0
            and build_report_path.stat().st_mtime_ns < builder_started_ns):
        report["status"] = "failed"
        report["report_error"] = "builder report predates this invocation"
        build_report = None
    if isinstance(build_report, dict):
        report["build_status"] = build_report.get("status")
        report["features"] = build_report.get("features", {})
        report["build_inputs"] = build_report.get("inputs", {})
        report["build_artifacts"] = build_report.get("artifacts", [])
        if build_report.get("status") == "failed":
            report["status"] = "failed"
        elif build_report.get("status") in {"not_ready", "partial_not_ready"}:
            report["status"] = build_report.get("status")

    if args.run_guest and report["status"] in {"built_not_run", "partial_not_ready"}:
        features = report.get("features", {})
        built_features = [name for name, value in features.items()
                          if isinstance(value, dict) and value.get("status") == "built_not_run"]
        if not built_features:
            report["status"] = "not_ready"
            report["guest_execution"] = "not_run: no hash-verified built_not_run ELFs"
        else:
            for name in built_features:
                entry = features[name]
                elf = Path(str(entry.get("elf", ""))).resolve()
                if output_root not in elf.parents or not elf.is_file():
                    report["status"] = "failed"
                    report["guest_execution"] = "not_run: ELF path missing or outside output-root"
                    break
                actual_hash = hashlib.sha256(elf.read_bytes()).hexdigest()
                if actual_hash != entry.get("sha256"):
                    report["status"] = "failed"
                    report["guest_execution"] = f"not_run: ELF hash mismatch for {name}"
                    break
                entry["host_elf_verified_sha256"] = actual_hash

            if report["status"] != "failed":
                try:
                    import e08_storage_smoke
                    from make_work_disk import create_fat32
                    from process_smoke import command as guest_command, resources
                    from work_disk import transfer
                    from boot_smoke import Guest

                    build_dir = ROOT / "build"
                    os_manifest = json.loads((build_dir / "manifest.json").read_text(encoding="utf-8"))
                    image_path = build_dir / "xos.img"
                    image_info = os_manifest.get("artifacts", {}).get("xos.img", {})
                    image_hash = hashlib.sha256(image_path.read_bytes()).hexdigest()
                    if image_hash != image_info.get("sha256"):
                        raise AssertionError("current XOS image does not match build/manifest.json")
                    report["xos_image"] = {"path": str(image_path), "sha256": image_hash,
                                           "build_id": os_manifest.get("build_id")}
                    with tempfile.TemporaryDirectory(prefix="xos_cpp_abi_") as folder:
                        disk = Path(folder) / "cpp_abi_work.img"
                        create_fat32(disk, 512)
                        transfer(disk, "mkdir", "/bin")
                        for name in built_features:
                            source = Path(str(features[name]["elf"]))
                            guest_name = f"cpp_abi_{name}.elf"
                            transfer(disk, "import", f"/bin/{guest_name}", source)
                        guest = e08_storage_smoke.boot(disk, "cpp_abi_smoke")
                        try:
                            baseline = resources(guest)
                            report["baseline_resources"] = baseline
                            report["guest_execution"] = "running"
                            for name in built_features:
                                guest_elf = Path(f"cpp_abi_{name}.elf")
                                try:
                                    run_result = check_guest_feature(
                                        guest, name, guest_elf, baseline, resources, guest_command
                                    )
                                except Exception as exc:
                                    report["features"][name]["status"] = "failed"
                                    report["features"][name]["error"] = str(exc)
                                    raise
                                report["features"][name].update(run_result)
                            final_resources = resources(guest)
                            report["final_resources"] = final_resources
                            if final_resources != baseline:
                                raise AssertionError(f"final guest resources differ from baseline: {final_resources} != {baseline}")
                            report["guest_execution"] = "completed"
                        finally:
                            guest.close()
                except Exception as exc:
                    report["status"] = "failed"
                    report["guest_execution"] = "failed"
                    report["error"] = str(exc)
                else:
                    not_ready_features = [name for name, value in features.items()
                                          if isinstance(value, dict) and value.get("status") == "not_ready"]
                    report["status"] = "partial_not_ready" if not_ready_features else "passed"
                    report["guest_execution"] = "passed" if not not_ready_features else "partial"

    output_root.mkdir(parents=True, exist_ok=True)
    report_path = output_root / "cpp_abi_smoke_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if report["status"] == "failed":
        print(f"FAILED report={report_path}")
        return 1
    if report["status"] in {"not_ready", "partial_not_ready"}:
        print(f"NOT_READY report={report_path}")
        return 2
    if report["status"] == "passed":
        print(f"PASS: {len(report['features'])} selected C++ ABI guest features | report={report_path}")
        return 0
    print(f"BUILT_NOT_RUN report={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
