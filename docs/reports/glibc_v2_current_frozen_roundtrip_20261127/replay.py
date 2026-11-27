"""Replay the previously bound workspace disks and current ISO without building."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

from build_candidate import inspect_app_kit
from glibc_newlib_frozen_rollback_guest import FROZEN_PROFILE, FROZEN_RELEASE
from glibc_newlib_frozen_rollback_guest import executable, guest_run, readback as fixture_readback, verify_release_file
from package_p2_faults import sparse_copy
from shell_launch_support import bind_system
from work_disk import host_tool as fat_tool
from xypm_format import canonical, load_json, require, sha_file
from xypm_image import Disk, host_tool as xypm_tool

args = argparse.ArgumentParser(description=__doc__)
args.add_argument("--inputs-only", action="store_true")
args = args.parse_args()
scratch = Path("/scratch")
out = Path("/out")
candidate = Path("/candidate")
system = candidate / "system"
v2_source = Path("/v2-fixture")
v2_disk = v2_source / "glibc-work.img"
kit = Path("/kit")
frozen = Path("/frozen")
media = frozen / "xylophoneos_revival_0.0.1-1024_images"
old_boot, released_disk = media / "xos.img", media / "work_disk.img"
old_package = frozen / "frozen.xpk"
historical = Path("/historical")
old_disk = historical / "guest-05/old-work.img"
old_sdk = historical / "xylophoneos_revival_0.0.1-1024_sdk"
historical_report = historical / "guest-05/report.json"
prior_report = Path("/workspace/docs/reports/glibc_v2_workspace_default_20261127/selection.json")
prefix = [sys.executable, "-B", "/workspace/scripts/xos_sdk.py", "--state", str(scratch / "selection.json")]

def command(*parts, reject=None):
    result = subprocess.run([*prefix, *map(str, parts)], capture_output=True, text=True)
    if reject:
        require(result.returncode != 0 and reject in result.stderr, f"expected {reject}: {result.stderr}")
    else:
        require(result.returncode == 0, f"operation failed: {parts[0]}: {result.stderr}")
    return json.loads(result.stdout) if result.stdout.startswith("{") else result.stdout

def readback(disk, path, target):
    if not args.inputs_only:
        return fixture_readback(disk, path, target)
    with Disk(disk, scratch, read_only=True) as backend:
        return backend.export(path).read_bytes()

def sha_file_marker(disk, path, target):
    return hashlib.sha256(readback(disk, path, target)).hexdigest()

def run_guest(*parameters, **options):
    memory = Path("/proc/meminfo").read_text().splitlines()
    available, = (int(line.split()[1]) for line in memory if line.startswith("MemAvailable:"))
    require(available >= 3670016, f"guest memory gate: MemAvailable={available} KiB")
    report.setdefault("guest_launch_memory_kib", []).append(available)
    return guest_run(*parameters, **options)


report = {"status": "failed", "source_commit": "960fce4347f193f13f5214caee153a03891ab100", "guests": {}, "guards": []}
private_out = scratch / "guest"
private_out.mkdir()
try:
    release = load_json(FROZEN_RELEASE)
    earlier = load_json(historical_report)
    qualified = load_json(prior_report)
    previous = earlier["frozen"]
    new = load_json(candidate / "candidate_manifest.json")
    kit_binding = inspect_app_kit(kit)
    require(new["source_commit"] == report["source_commit"] and new["installer_guest_qualification"] == "passed"
            and new["application_sdk"] == kit_binding, "current system or v2 kit differs from candidate")
    current = bind_system(system)
    require(current["build_id"] == new["build_id"] and
            sha_file(system / "manifest.json") == new["artifacts"]["system/manifest.json"] and
            sha_file(system / "xos-install.iso") == new["artifacts"]["system/xos-install.iso"],
            "current system did not bind to the exact candidate")
    frozen_boot_sha = verify_release_file(release, old_boot, "_boot.img")
    images_sha = verify_release_file(release, frozen / "release-images.tar.gz", "_images.tar.gz")
    sdk_sha = verify_release_file(release, Path("/frozen-sdk.tar.gz"), "_sdk.tar.gz")
    old_binding = executable(old_package, FROZEN_PROFILE, "/usr/bin/frozen")
    disk_inputs = {"v2": sha_file(v2_disk), "previous_user_disk": sha_file(old_disk), "release_unmarked": sha_file(released_disk)}
    require(sha_file(historical_report) == qualified["previous_frozen_report_sha256"]
            and frozen_boot_sha == previous["boot_sha256"] == qualified["frozen_boot_sha256"]
            and images_sha == previous["images_archive_sha256"]
            and sdk_sha == previous["sdk_archive_sha256"]
            and sha_file(FROZEN_PROFILE) == previous["profile_sha256"]
            and disk_inputs["v2"] == qualified["glibc_disk_sha256"]
            and disk_inputs["previous_user_disk"] == previous["disk_after_rollback_sha256"]
            == qualified["original_frozen_disk_sha256"]
            and disk_inputs["release_unmarked"] == previous["published_disk_sha256"] == qualified["unmarked_release_disk_sha256"]
            and old_binding["package_sha256"] == previous["application"]["package_sha256"]
            == qualified["reproduced_frozen_xpk_sha256"], "frozen source, disks or old package differ")
    packages = {}
    for language in ("c", "cpp"):
        packages[language] = executable(v2_source / (language + ".xpk"), kit / "profile.json",
                                        "/usr/bin/kit_" + language, binding=kit_binding)
        require(packages[language] == qualified["glibc_packages"][language],
                "qualified v2 fixture package differs: " + language)
    report.update(current={"build_id": current["build_id"],
                           "manifest_sha256": sha_file(system / "manifest.json"),
                           "candidate_manifest_sha256": sha_file(candidate / "candidate_manifest.json"),
                           "ordinary_iso_sha256": sha_file(system / "xos-install.iso"),
                           "kit": kit_binding, "source_files": len(current["sources"])},
                  frozen={"release": "0.0.1-1024", "build_id": release["system_build_id"], "boot_sha256": frozen_boot_sha,
                          "images_archive_sha256": images_sha, "sdk_archive_sha256": sdk_sha,
                          "prior_report_sha256": sha_file(historical_report),
                          "profile_sha256": sha_file(FROZEN_PROFILE), "package": old_binding},
                  original_disks=disk_inputs, v2_packages=packages,
                  prior_v2_selection_sha256=sha_file(prior_report))

    # Existing FAT tools are copied into the validated caches. The launcher's
    # compiler guards ensure a stale cache cannot silently cause a new build.
    report["host_tools"] = {"work_disk_host_sha256": sha_file(fat_tool(build=False)),
                            "xypm_disk_host_sha256": sha_file(xypm_tool())}
    configured = scratch / "configured-kit"
    shutil.copytree(kit, configured, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    state = scratch / "selection.json"
    start = command("setup", "--glibc-kit", configured, "--newlib-sdk", old_sdk)
    require(start["active"] == "glibc", "incorrect initial SDK")
    for family, binding in start["bindings"].items():
        require({key: val for key, val in binding.items() if key != "root"} == qualified["bindings"][family],
                "initial SDK differs from the accepted binding")
    selected_sha = sha_file(state)
    command("setup", "--glibc-kit", configured, "--newlib-sdk", old_sdk, reject="File exists")
    require(sha_file(state) == selected_sha, "setup rewrote the existing registry")
    report["sdk_bindings"] = {key: {name: value for name, value in binding.items() if name != "root"}
                              for key, binding in start["bindings"].items()}
    command("xypm", "verify", old_package, reject="package target profile mismatch")
    command("xypm", "verify", old_package, "--prof", FROZEN_PROFILE, reject="supplies its own")
    command("xypm", "verify-installed", "--image", old_disk, reject="database profile mismatch")
    command("xypm", "verify-installed", "--image", v2_disk)
    report["guards"].extend(["v2_rejects_frozen_package", "v2_rejects_profile_override",
                             "v2_rejects_frozen_database", "v2_reads_qualified_database"])
    unmarked = scratch / "unmarked.img"
    sparse_copy(released_disk, unmarked)
    require(sha_file(unmarked) == disk_inputs["release_unmarked"], "unmarked copy differs")
    refused1, refused2 = scratch / "refused.img", scratch / "refused-repo.img"
    no_profile = "work disk has no xypm profile"
    command("xypm", "list", "--image", unmarked, reject=no_profile)
    command("xypm", "install", v2_source / "c.xpk", "--offline", "--image", unmarked,
            "--output-image", refused1, reject=no_profile)
    command("xypm", "repo-install", v2_source / "repository", v2_source / "lock.json", "selection.kit_c",
            "--offline", "--image", unmarked, "--output-image", refused2, reject=no_profile)
    require(sha_file(unmarked) == disk_inputs["release_unmarked"] and not refused1.exists() and not refused2.exists(),
            "rejected operations changed the unmarked disk or made output")
    unmarked.unlink()
    report["guards"].extend(["unmarked_list_rejected", "unmarked_install_rejected", "unmarked_repo_install_rejected"])

    v2 = scratch / "glibc-work.img" if not args.inputs_only else v2_disk
    old = scratch / "frozen-work.img" if not args.inputs_only else old_disk
    marker = scratch / "readback"
    if not args.inputs_only:
        sparse_copy(v2_disk, v2)
        sparse_copy(old_disk, old)
        require(sha_file(v2) == disk_inputs["v2"] and sha_file(old) == disk_inputs["previous_user_disk"],
                "QEMU scratch disks differ from their bound originals")
    old_user = readback(old, "/state/user.txt", marker)
    new_user = readback(v2, "/state/user.txt", marker)
    require(new_user == b"glibc-user-data\n", "old v2 fixture data differs")
    image = system / "xos-install.iso"
    new_commands = [("exec-file /usr/bin/kit_c", b"GLIBC_KIT_C_OK 2.44"),
                    ("exec-file /usr/bin/kit_cpp", b"GLIBC_KIT_CPP_OK vector thread exception")]
    report["boot_parameters"] = {"v2": {"media": "ordinary_iso", "cpu": "qemu64,+rdrand", "commands": [i[0] for i in new_commands]},
                                 "frozen": {"media": "release_boot_floppy", "cpu": "qemu64",
                                            "commands": ["exec-file /usr/bin/frozen selection"]}}
    if not args.inputs_only:
        report["guests"]["v2_before"] = run_guest(private_out, image, v2, "v2_before", current["build_id"], new_commands)
    disk_seen = sha_file(v2)
    unavailable = scratch / "unavailable"
    configured.rename(unavailable)
    try:
        command("status", reject="SDK must be a real directory")
        require(load_json(state)["active"] == "glibc", "missing kit changed selection")
        command("use", "newlib")
        rolled_back = sha_file(state)
        command("use", "glibc", reject="SDK must be a real directory")
        require(load_json(state)["active"] == "newlib" and sha_file(state) == rolled_back,
                "failed selection changed the frozen binding")
        require(sha_file(old) == disk_inputs["previous_user_disk"] and sha_file(v2) == disk_seen,
                "selection changed disk bytes")
        command("xypm", "verify", v2_source / "c.xpk", reject="package target profile mismatch")
        command("xypm", "verify-installed", "--image", v2, reject="database profile mismatch")
        command("xypm", "verify-installed", "--image", old)
        require(sha_file_marker(old, "/usr/bin/frozen", marker) == old_binding["elf_sha256"],
                "installed frozen ELF differs")
        report["guards"].extend(["missing_kit_fails_closed", "newlib_rejects_v2_package",
                                 "newlib_rejects_v2_database", "newlib_reads_frozen_database"])
        if not args.inputs_only:
            report["guests"]["newlib"] = run_guest(private_out, old_boot, old, "newlib", release["system_build_id"],
                  [("exec-file /usr/bin/frozen selection", b"FROZEN_RUNTIME_OK selection")], historical=True)
            require(readback(old, "/state/user.txt", marker) == old_user + b"selection\n",
                    "frozen guest did not preserve and update the original user data")
            command("xypm", "verify-installed", "--image", old)
    finally:
        unavailable.rename(configured)
    old_final = sha_file(old)
    command("use", "glibc")
    require(sha_file(state) == selected_sha and sha_file(v2) == disk_seen and sha_file(old) == old_final,
            "restored v2 selection changed a working disk or SDK binding")
    if not args.inputs_only:
        report["guests"]["v2_after"] = run_guest(private_out, image, v2, "v2_after", current["build_id"], new_commands)
    command("xypm", "verify-installed", "--image", v2)
    require(readback(v2, "/state/user.txt", marker) == new_user, "v2 guest user data changed")
    require(sha_file(v2_disk) == disk_inputs["v2"] and sha_file(old_disk) == disk_inputs["previous_user_disk"]
            and sha_file(released_disk) == disk_inputs["release_unmarked"], "an original disk changed")
    report["source_disks_preserved"] = True
    report["data_sha256"] = {"v2": hashlib.sha256(new_user).hexdigest(),
                             "old_before": hashlib.sha256(old_user).hexdigest(),
                             "old_after": hashlib.sha256(readback(old, "/state/user.txt", marker)).hexdigest()}
    report["status"] = "inputs_verified" if args.inputs_only else "passed"
finally:
    (out / ("inputs.json" if args.inputs_only else "report.json")).write_bytes(canonical(report))
