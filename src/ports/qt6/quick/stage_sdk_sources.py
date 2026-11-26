#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Recover the upstream archives and exact XOS inputs of a Qt kit's glibc SDK."""

import argparse
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile

from quick_kit import ROOT, fingerprint
from relink import json_read, manifest_file, sha

sys.path.insert(0, str(ROOT / "scripts"))
from xypm_sdk_profile import verify_profile


def git_source(revision, inputs):
    commit = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "--verify", revision + "^{commit}"], text=True).strip()
    packed = subprocess.check_output(["git", "-C", str(ROOT), "archive", "--format=tar", commit, "--", *inputs])
    files = {}
    with tarfile.open(fileobj=io.BytesIO(packed), mode="r:") as snapshot:
        for item in snapshot:
            if not item.isdir():
                if not item.isfile() or item.name not in inputs or item.name in files:
                    raise ValueError(f"Unexpected archived SDK source {item.name}")
                files[item.name] = snapshot.extractfile(item).read()
    if files.keys() != inputs.keys():
        raise ValueError("Git source does not contain the complete SDK build input inventory")
    return commit, files


def verified_sdk(kit):
    kit_path = manifest_file(kit, "manifest.json")
    expected = json_read(kit_path)
    observed = fingerprint(kit)
    observed["input_application_receipt_sha256"] = sha(manifest_file(kit, "input_application_receipt.json"))
    if observed != expected:
        raise ValueError("The Qt Quick kit differs from its manifest")
    sdk = kit / "runtime/sdk"
    profile = json_read(manifest_file(kit, "runtime/profile.json"))
    verify_profile(profile, "glibc", sdk)
    return sdk, sha(kit_path), observed["sdk_manifest_sha256"]


def stage(args):
    kit = args.kit.resolve(strict=True)
    output = args.output.resolve()
    if output.is_relative_to(kit) or args.output.is_symlink():
        raise ValueError("Choose a distinct output outside the Qt Quick kit")
    sdk, kit_digest, sdk_digest = verified_sdk(kit)
    sdk_manifest = json_read(sdk / "manifest.json")
    sources = {
        "glibc": (args.glibc_source, sdk_manifest["source_sha256"], "source_verification",
                  sdk_manifest["source_verification_report_sha256"]),
        "gcc": (args.gcc_source, sdk_manifest["cxx_runtime"]["source_sha256"], "gcc_source_verification",
                sdk_manifest["cxx_source_verification_report_sha256"]),
    }
    for component, (archive, digest, reports, report_digest) in sources.items():
        report = manifest_file(sdk, reports + "/report.json")
        if (sha(archive) != digest or sha(report) != report_digest
                or json_read(report).get("archive_sha256") != digest
                or json_read(report).get("status") != "upstream_signature_verified"):
            raise ValueError(f"{component} source or verification report differs from the SDK")

    inputs = sdk_manifest["inputs"]
    for relative in inputs:
        path = PurePosixPath(relative)
        if not path.parts or path.is_absolute() or ".." in path.parts:
            raise ValueError(f"Invalid original SDK build input {relative}")
    revision, files = git_source(args.sdk_revision, inputs)
    output.mkdir(parents=True, exist_ok=False)
    try:
        for name, data in files.items():
            path = output / "xos" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            if sha(path) != inputs[name]:
                raise ValueError(f"XOS source differs from the SDK build for {name}")

        share = output / "installed_source_and_notices"
        shutil.copytree(sdk / "sysroot/usr/share/xos-glibc", share)
        shutil.copyfile(sdk / "manifest.json", output / "sdk_manifest.json")
        shutil.copyfile(kit / "runtime/profile.json", output / "sdk_profile.json")
        shutil.copyfile(kit / "runtime/NOTICE", output / "sdk_notice.txt")
        archives = output / "upstream"
        archives.mkdir()
        material = {}
        for component, (archive, digest, reports, report_digest) in sources.items():
            # The destination name is resolved from the original installed source lock.
            lock = share / ("port/source_lock.json" if component == "glibc" else "cxx/port/source_lock.json")
            lock_metadata = json_read(lock)
            name_key, digest_key = ("archive", "archive_sha256") if component == "glibc" else ("source_archive", "sha256")
            if lock_metadata[digest_key] != digest:
                raise ValueError(f"The installed {component} source lock differs from the SDK")
            name = lock_metadata[name_key]
            if PurePosixPath(name).name != name or not name.endswith(".tar.xz"):
                raise ValueError("Unexpected SDK source archive filename")
            shutil.copyfile(archive, archives / name)
            if sha(archives / name) != digest:
                raise ValueError(f"{component} source changed during staging")
            shutil.copytree(sdk / reports, output / reports)
            if sha(output / reports / "report.json") != report_digest:
                raise ValueError(f"{component} verification report changed during staging")
            material[component] = {"name": name, "sha256": digest, "original_report_sha256": report_digest}

        if verified_sdk(kit)[1:] != (kit_digest, sdk_digest):
            raise ValueError("The Qt Quick kit or SDK changed during staging")
        report = {"status": "upstream_and_xos_sdk_sources_staged", "kit_manifest_sha256": kit_digest,
                  "sdk_manifest_sha256": sdk_digest, "xos_sdk_source_commit": revision,
                  "xos_input_files": len(files), "upstream": material,
                  "compiler_seed_runtime_sha256": {name: value["sha256"]
                      for name, value in sdk_manifest["compiler_runtime"].items() if "sha256" in value},
                  "cxx_runtime_rebuild": "not_run", "compiler_seed_rebuild": "not_run",
                  "files": {path.relative_to(output).as_posix(): sha(path)
                            for path in sorted(output.rglob("*")) if path.is_file()}}
        (output / "manifest.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    except Exception:
        shutil.rmtree(output)
        raise
    print(sha(output / "manifest.json"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("kit", "output", "glibc-source", "gcc-source"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--sdk-revision", required=True)
    stage(parser.parse_args())


if __name__ == "__main__":
    main()
