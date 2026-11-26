#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the locked synchronous Test262 cases in fresh JavaScriptCore processes."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import send_bytes
from work_disk import transfer

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "src/ports/webkit/test262_lock.json"
MARKER = b"XOS_TEST262_CASE_COMPLETE"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def stage(disk, work, inputs, lock, payload):
    files = {"/tc/jsc": payload}
    required = set(lock["default_harness"])
    for case in lock["cases"]:
        required.update(case["includes"])
    for name in sorted(required):
        harness_file = work / name
        harness_file.write_bytes(inputs[f"harness/{name}"])
        files[f"/tc/{name}"] = harness_file
    marker = work / "complete.js"
    marker.write_bytes(b'print("' + MARKER + b'");\n')
    files["/tc/complete.js"] = marker
    staged = []
    for number, case in enumerate(lock["cases"]):
        raw = inputs[case["path"]]
        for mode, prefix in (("sloppy", b""), ("strict", b'"use strict";\n')):
            temporary = work / f"case{number}_{mode}.js"
            temporary.write_bytes(prefix + raw)
            script = f"/tc/{temporary.name}"
            files[script] = temporary
            harness = [f"/tc/{name}" for name in (*lock["default_harness"], *case["includes"])]
            arguments = " ".join([*harness, script, "/tc/complete.js"])
            staged.append((case["path"], mode, script, arguments))

    expected = {path: sha(source) for path, source in files.items()}
    create_fat32(disk, 512)
    transfer(disk, "mkdir", "/tc")
    for path, source in files.items():
        transfer(disk, "import", path, source)

    readback = work / "readback"
    verified = {}
    for path, digest in expected.items():
        transfer(disk, "export", path, readback)
        verified[path] = sha(readback)
        readback.unlink()
        if verified[path] != digest:
            raise ValueError(f"FAT readback differs from the staged input: {path}")
    return staged, verified


def run_cases(guest, baseline, staged, verified, cases):
    for filename, mode, script, arguments in staged:
        output = command(guest, f"exec-file /tc/jsc {arguments}", b"[wait] pid=", timeout=180)
        launch = re.search(rb"\[loader\] started pid=(\d+) file=/tc/jsc\b", output)
        if launch is None:
            raise RuntimeError(f"the shell did not launch the engine for {filename} ({mode})")
        pid = launch.group(1)
        wait = re.findall(rb"\[wait\] pid=" + pid + rb" kind=(\w+) code=(-?\d+)", output)
        if len(wait) != 1:
            raise RuntimeError(f"missing process outcome for {filename} ({mode})")
        kind, code = wait[0][0].decode(), int(wait[0][1])
        completed = output.replace(b"\r", b"").splitlines().count(MARKER) == 1
        after = resources(guest)
        passed = (kind, code) == ("exited", 0) and completed and after == baseline
        cases.append({"test": filename, "mode": mode, "guest_script_sha256": verified[script],
                      "kind": kind, "code": code, "completion_marker": completed,
                      "resources_after": after, "status": "passed" if passed else "failed"})
        if after != baseline:
            raise RuntimeError(f"resources changed after {filename} ({mode})")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("system", "payload", "engine-binding", "suite", "report"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--expected-resources", nargs=3, type=int, required=True,
                        metavar=("PAGES", "TASKS", "COMPLETIONS"))
    args = parser.parse_args()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    lock = json.loads(LOCK.read_bytes())
    report = {"status": "failed", "cases": [], "test262_commit": lock["commit"],
              "source_lock_sha256": sha(LOCK), "runner_sha256": sha(Path(__file__)),
              "scheduled": 2 * len(lock["cases"]), "expected_resources": args.expected_resources}
    guest = None
    try:
        inputs = {}
        for name, expected in lock["files"].items():
            data = (args.suite / name).read_bytes()
            if hashlib.sha256(data).hexdigest() != expected:
                raise ValueError(f"Test262 input differs from the source lock: {name}")
            inputs[name] = data
        image = args.system / "xos-install.iso"
        manifest = args.system / "manifest.json"
        system_bytes = manifest.read_bytes()
        binding_bytes = args.engine_binding.read_bytes()
        system = json.loads(system_bytes)
        binding = json.loads(binding_bytes)
        image_sha = system["artifacts"]["xos-install.iso"]["sha256"]
        payload_sha = binding["static_elf_sha256"]
        report.update(system_build=system["build_id"], system_manifest_sha256=hashlib.sha256(system_bytes).hexdigest(),
                      iso_sha256=image_sha, jsc_sha256=payload_sha,
                      engine_binding_sha256=hashlib.sha256(binding_bytes).hexdigest(),
                      sdk_manifest_sha256=binding["glibc_sdk_manifest_sha256"])
        with tempfile.TemporaryDirectory(prefix="xos_test262_") as temporary:
            work = Path(temporary)
            disk = work / "work.img"
            frozen_image = work / "boot.iso"
            shutil.copyfile(image, frozen_image)
            if sha(frozen_image) != image_sha:
                raise ValueError("copied system image differs from its manifest")
            frozen_payload = work / "jsc.elf"
            shutil.copyfile(args.payload, frozen_payload)
            if sha(frozen_payload) != payload_sha:
                raise ValueError("copied JavaScriptCore ELF differs from its build binding")
            staged, verified = stage(disk, work, inputs, lock, frozen_payload)
            report["fat_readback_sha256"] = verified
            guest = Guest(frozen_image, "test262", work_disk=disk, log_dir=args.report.parent)
            try:
                report["qemu_version"] = subprocess.check_output(
                    [guest.command[0], "--version"], text=True).splitlines()[0]
                guest.expect(b"xos64> ", timeout=60)
                send_bytes(guest, b"run\r")
                guest.expect_supervisor(trace=True, timeout=60)
                command(guest, "demo quiet", b"demo tasks")
                baseline = resources(guest)
                report["baseline"] = baseline
                if baseline != tuple(args.expected_resources):
                    raise RuntimeError("the selected system did not reach the expected guest baseline")
                run_cases(guest, baseline, staged, verified, report["cases"])
                report["passed"] = sum(case["status"] == "passed" for case in report["cases"])
                if report["passed"] == report["scheduled"]:
                    report["status"] = "passed_subset"
            finally:
                guest.close()
    finally:
        if guest is not None:
            serial = bytes(guest.output)
            args.report.with_suffix(".serial.log").write_bytes(serial)
            report["serial_sha256"] = hashlib.sha256(serial).hexdigest()
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    if report["status"] != "passed_subset":
        raise SystemExit("the locked Test262 subset did not pass")
    print(f"PASS {report['passed']}/{report['scheduled']} locked Test262 executions")


if __name__ == "__main__":
    main()
