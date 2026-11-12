# SPDX-License-Identifier: Apache-2.0
"""Shared input binding and guest checks for the native development gates."""
from pathlib import Path
import hashlib
import json
import re
import sys

repo_root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(repo_root / "scripts"), str(repo_root / "tests")]
from seed_preflight import validate_bundle
from work_disk import transfer
from process_smoke import command, resources
from task_smoke import send_bytes, pump


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def relative_file(root, name):
    path = Path(name)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError("receipt file must be relative to its declared root: " + str(name))
    source = root / path
    if source.is_symlink() or not source.resolve(strict=True).is_relative_to(root.resolve()):
        raise ValueError("receipt file escapes its declared root: " + str(name))
    if not source.is_file():
        raise ValueError("receipt input is not a file: " + str(name))
    return source


def check_hash(path, expected, label):
    if not isinstance(expected, str) or sha(path) != expected:
        raise ValueError(label + " hash differs: " + str(path))


def bind_system(system, workspace=repo_root):
    system = system.resolve(strict=True)
    manifest = json.loads((system / "manifest.json").read_text())
    if not manifest.get("sources") or not manifest.get("artifacts"):
        raise ValueError("system manifest must bind sources and artifacts")
    for name, digest in manifest["sources"].items():
        check_hash(relative_file(workspace, name), digest, "system source")
    required = {"xos-install.iso", "sdk/manifest.json", "sdk/crt0_posix.o",
                "sdk/user.ld", "sdk/lib/libxos.a", "sdk/lib/libxos_loader.a",
                "sdk/lib/libc.a", "sdk/lib/libm.a"}
    if not required <= manifest["artifacts"].keys():
        raise ValueError("system manifest lacks the complete application SDK")
    for name, entry in manifest["artifacts"].items():
        check_hash(relative_file(system, name), entry["sha256"], "system artifact")
    sdk = system / "sdk"
    sdk_files = {"sdk/" + str(path.relative_to(sdk)) for path in sdk.rglob("*") if path.is_file()}
    if sdk_files != {name for name in manifest["artifacts"] if name.startswith("sdk/")}:
        raise ValueError("SDK file inventory differs from the system manifest")
    if json.loads((sdk / "manifest.json").read_text()).get("build_id") != manifest["build_id"]:
        raise ValueError("SDK and system build IDs differ")
    return manifest


def bind_tool(receipt_path, profile, sdk, workspace=repo_root):
    receipt = json.loads(receipt_path.read_text())
    if receipt.get("profile") != profile or receipt.get("status") != "built_not_run":
        raise ValueError("unexpected tool build receipt profile/status: " + str(receipt_path))
    inputs = receipt.get("inputs", {})
    sdk_inputs = {"sdk/" + str(path.relative_to(sdk)) for path in sdk.rglob("*") if path.is_file()}
    if not sdk_inputs or sdk_inputs != {name for name in inputs if name.startswith("sdk/")}:
        raise ValueError("tool receipt must bind this complete SDK tree")
    for name, digest in inputs.items():
        source = relative_file(sdk, name[4:]) if name.startswith("sdk/") else relative_file(workspace, name)
        check_hash(source, digest, "tool input")
    if "sdk_manifest_sha256" in receipt:
        check_hash(sdk / "manifest.json", receipt["sdk_manifest_sha256"], "tool SDK")
    artifact = relative_file(workspace, receipt["elf"])
    check_hash(artifact, receipt["sha256"], "tool ELF")
    return artifact, {"receipt": str(receipt_path), "receipt_sha256": sha(receipt_path),
                      "elf": str(artifact), "elf_sha256": receipt["sha256"],
                      "sdk_manifest_sha256": inputs["sdk/manifest.json"]}


def add_arguments(parser):
    parser.add_argument("--system", type=Path, default=repo_root / "build")
    parser.add_argument("--make-receipt", type=Path, required=True)
    parser.add_argument("--dash-receipt", type=Path, required=True)
    parser.add_argument("--seed-manifest", type=Path, required=True)
    parser.add_argument("--seed-root", type=Path, required=True)
    parser.add_argument("--sysroot-manifest", type=Path, required=True)
    parser.add_argument("--sysroot-root", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")


def bind_native_inputs(args, report):
    system = bind_system(args.system)
    sdk = args.system / "sdk"
    make, make_binding = bind_tool(args.make_receipt, "sbase_make_xos_explicit_always_build_v1", sdk)
    dash, dash_binding = bind_tool(args.dash_receipt, "dash_c3", sdk)
    required = ("gcc", "cc1", "g++", "cc1plus", "as", "ld", "ar", "ranlib")
    checked = validate_bundle(args.seed_manifest, args.seed_root, args.sysroot_manifest,
                              args.sysroot_root, "/sysroot", required)
    report["seed_preflight"] = checked.to_dict()
    if not checked.ok:
        if all(item["code"] in ("source_file", "manifest_read") for item in checked.diagnostics):
            raise FileNotFoundError("declared Seed/sysroot inputs are unavailable")
        raise ValueError("Seed/sysroot preflight failed; see seed_preflight diagnostics")
    seed = json.loads(args.seed_manifest.read_text())
    sysroot = json.loads(args.sysroot_manifest.read_text())
    current_sdk = sha(sdk / "manifest.json")
    sdk_binding = seed["sdk_manifest"]
    expected = sdk_binding["sha256"] if isinstance(sdk_binding, dict) else seed["sdk_manifest_sha256"]
    if expected != current_sdk or sysroot.get("sdk_manifest_sha256") != current_sdk:
        raise ValueError("Seed application sysroot must bind the selected system SDK")
    covered = set()
    for name, digest in seed.get("input_manifests", {}).items():
        path = relative_file(args.seed_root, name)
        check_hash(path, digest, "Seed input receipt")
        receipt = json.loads(path.read_text())
        matching = {key for key in required if key in receipt.get("tools", {}) and
                    receipt["tools"][key].get("sha256") == seed["tools"][key]["sha256"]}
        if matching:
            binding = receipt.get("sdk_manifest")
            bound = binding.get("sha256") if isinstance(binding, dict) else receipt.get("sdk_manifest_sha256")
            if bound != current_sdk:
                raise ValueError("compiler/binutils must be rebuilt or relinked against this SDK: " + name)
            covered.update(matching)
    if set(required) != covered:
        raise ValueError("Seed must bind compiler and binutils build receipts via prepare_gcc_seed.py")
    for name in required:
        if re.fullmatch(r"/[A-Za-z0-9_./+\-]+", checked.tools[name]["guest_path"]) is None:
            raise ValueError("tool path is not usable as an ordinary command: " + name)
    installed = {item["guest_path"]: item["sha256"] for item in checked.sysroot_files}
    for path in sdk.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(sdk).as_posix()
        if relative.startswith("include/"):
            destination = "/sysroot/" + relative
        elif relative in ("crt0_posix.o", "user.ld", "lib/libxos.a", "lib/libxos_loader.a", "lib/libc.a", "lib/libm.a"):
            destination = "/sysroot/lib/" + path.name
        else:
            continue
        if installed.get(destination) != sha(path):
            raise ValueError("installed sysroot differs from selected SDK: " + destination)
    destinations = {item["guest_path"].casefold() for item in checked.seed_files + checked.sysroot_files}
    if destinations & {"/usr/bin/make", "/usr/bin/dash"}:
        raise ValueError("Seed must not overwrite the separately selected Make/dash")
    report["bindings"] = {"build_id": system["build_id"], "system_manifest_sha256": sha(args.system / "manifest.json"),
                          "iso_sha256": system["artifacts"]["xos-install.iso"]["sha256"],
                          "sdk_manifest_sha256": current_sdk, "make": make_binding, "dash": dash_binding,
                          "seed_manifest_sha256": sha(args.seed_manifest),
                          "sysroot_manifest_sha256": sha(args.sysroot_manifest)}
    return {"make": make, "dash": dash, "seed": checked.seed_files,
            "sysroot": checked.sysroot_files, "tools": checked.tools}


def install_files(disk, source_root, entries):
    directories = set()
    for item in entries:
        directories.update(str(path) for path in Path(item["guest_path"]).parents if str(path) != "/")
    for path in sorted(directories, key=lambda value: (value.count("/"), value)):
        transfer(disk, "mkdir", path)
    for item in entries:
        transfer(disk, "import", item["guest_path"], source_root / item["source_path"])


def boot_guest(guest):
    guest.expect(b"xos64> ", timeout=40)
    send_bytes(guest, b"run\r")
    guest.expect_supervisor(trace=True, timeout=40)
    command(guest, "demo quiet", b"[sup] demo tasks ")
    pump(guest, 0.5)


def check_result(output, expected, markers=()):
    matches = re.findall(rb"kind=exited code=(-?\d+)(?:\r?\n|$)", output)
    if not matches or (int(matches[-1]) == 0 if expected is None else int(matches[-1]) != expected):
        raise AssertionError("wrong or missing final exit status: " + repr(output[-3000:]))
    lines = output.splitlines()
    if any(marker not in lines for marker in markers):
        raise AssertionError("missing complete result line: " + repr(output[-3000:]))
    return int(matches[-1])


def run_case(guest, report, name, shell, line, markers=(), expected=0, timeout=240):
    before = resources(guest)
    row = {"name": name, "shell": shell, "command": line, "status": "failed"}
    report["checks"].append(row)
    output = command(guest, line, b"xsh> ", timeout=timeout)
    row["output"] = output.decode(errors="replace")
    row["exit_code"] = check_result(output, expected, markers)
    after = resources(guest)
    row["resources_before"], row["resources_after"] = before, after
    if before != after:
        raise AssertionError(name + " did not reclaim process/completion/pages resources")
    row["status"] = "passed"
    return output


def write_report(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")
    files = {str(item.relative_to(path.parent)): sha(item) for item in sorted(path.parent.rglob("*"))
             if item.is_file() and item.name != "manifest.json"}
    (path.parent / "manifest.json").write_text(json.dumps({"version": 1, "files": files}, indent=2) + "\n")
