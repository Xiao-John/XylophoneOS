# SPDX-License-Identifier: Apache-2.0
"""Build isolated C++ ABI probes from an explicit target runtime manifest.

This tool prepares XOS ELF files only. It never runs them; guest execution is
the only way a feature can be reported as passed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
from datetime import datetime, timezone
import os
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "cpp_abi"
FEATURES = {
    "string_vector": ("string_vector", ("string_vector_probe.cpp",)),
    "exceptions": ("exceptions", ("exception_probe.cpp",)),
    "rtti": ("rtti", ("rtti_probe.cpp",)),
    "local_static": ("local_static", ("local_static_probe.cpp",)),
    "tls_destructors": ("tls_destructors", ("tls_destructor_probe.cpp",)),
    "multi_tu": ("multi_tu", ("multi_tu_a.cpp", "multi_tu_b.cpp", "multi_tu_main.cpp")),
}


class ManifestError(Exception):
    pass


def reject_symlink_components(path: Path, label: str) -> None:
    absolute = Path(os.path.abspath(path.expanduser()))
    for component in reversed((absolute, *absolute.parents)):
        if component.is_symlink():
            raise ManifestError(f"{label} contains a symlink component: {component}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ManifestError(f"expected JSON object in {path}")
    return value


def checked_hash(path: Path, expected: str, label: str) -> str:
    if path.is_dir():
        digest = hashlib.sha256()
        for entry in sorted(path.rglob("*")):
            if entry.is_symlink():
                raise ManifestError(f"{label} contains a symlink; directory hashes must be self-contained")
            if entry.is_file():
                digest.update(entry.relative_to(path).as_posix().encode("utf-8"))
                digest.update(b"\0")
                digest.update(bytes.fromhex(sha256_file(entry)))
        actual = digest.hexdigest()
    elif path.is_file():
        actual = sha256_file(path)
    else:
        raise ManifestError(f"{label} is missing: {path}")
    if actual.lower() != str(expected).lower():
        raise ManifestError(f"{label} sha256 mismatch: expected {expected}, got {actual}")
    return actual


def resolve_artifact(item: Any, sdk_root: Path, runtime_root: Path, label: str) -> tuple[Path, str]:
    if not isinstance(item, dict) or item.get("root") not in {"sdk", "runtime"}:
        raise ManifestError(f"{label} must specify root='sdk' or root='runtime' and path/sha256")
    base = sdk_root if item["root"] == "sdk" else runtime_root
    relative = Path(str(item.get("path", "")))
    if not relative.parts or relative.is_absolute() or ".." in relative.parts:
        raise ManifestError(f"{label} path must be relative and stay inside its declared root")
    unresolved_path = base / relative
    reject_symlink_components(unresolved_path, label)
    path = unresolved_path.resolve()
    try:
        path.relative_to(base.resolve())
    except ValueError as exc:
        raise ManifestError(f"{label} escapes its declared root") from exc
    digest = checked_hash(path, str(item.get("sha256", "")), label)
    return path, digest


def parse_string_list(value: Any, label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ManifestError(f"{label} must be an array of strings")
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", required=True, type=Path, help="immutable SDK root")
    parser.add_argument("--runtime-prefix", required=True, type=Path, help="target C++ runtime prefix")
    parser.add_argument("--runtime-manifest", required=True, type=Path, help="runtime manifest JSON")
    parser.add_argument("--output-root", required=True, type=Path, help="explicit writable output directory")
    parser.add_argument("--features", default=",".join(FEATURES), help="comma-separated probe feature names")
    return parser.parse_args()


def write_report(output_root: Path, report: dict[str, Any]) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    path = output_root / "cpp_abi_build_report.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    selected = [item.strip() for item in args.features.split(",") if item.strip()]
    unknown = sorted(set(selected) - set(FEATURES))
    if unknown or not selected:
        print(f"invalid --features selection: unknown={unknown}, empty={not selected}", file=sys.stderr)
        return 2

    try:
        reject_symlink_components(args.sdk, "--sdk")
        reject_symlink_components(args.runtime_prefix, "--runtime-prefix")
        reject_symlink_components(args.runtime_manifest, "--runtime-manifest")
        reject_symlink_components(args.output_root, "--output-root")
    except ManifestError as exc:
        print(f"NOT_READY: {exc}", file=sys.stderr)
        return 2
    sdk_root = args.sdk.resolve()
    runtime_root = args.runtime_prefix.resolve()
    manifest_path = args.runtime_manifest.resolve()
    output_root = args.output_root.resolve()
    report: dict[str, Any] = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "not_ready",
        "execution": "host cross-compile preparation; guest execution not performed",
        "features": {name: {"status": "not_run", "reason": "preflight pending"} for name in selected},
        "commands": [],
        "artifacts": [],
    }

    try:
        if not sdk_root.is_dir():
            raise ManifestError(f"SDK root does not exist: {sdk_root}")
        if not manifest_path.is_file():
            raise ManifestError(f"runtime manifest does not exist: {manifest_path}")
        if output_root == sdk_root or sdk_root in output_root.parents:
            raise ManifestError("output-root must not be inside the immutable SDK")
        if output_root == runtime_root or runtime_root in output_root.parents:
            raise ManifestError("output-root must not be inside the target runtime prefix")
        manifest = load_json(manifest_path)
        report["inputs"] = {
            "sdk": str(sdk_root),
            "runtime_prefix": str(runtime_root),
            "runtime_manifest": str(manifest_path),
            "runtime_manifest_sha256": sha256_file(manifest_path),
            "selected_features": selected,
            "runtime_provenance": manifest.get("provenance", {}),
            "runtime_build_flags": manifest.get("runtime_build_flags", []),
        }
        sdk_binding = manifest.get("sdk_manifest")
        if not isinstance(sdk_binding, dict):
            raise ManifestError("manifest.sdk_manifest must bind path and sha256")
        sdk_manifest_rel = Path(str(sdk_binding.get("path", "")))
        if sdk_manifest_rel.is_absolute() or ".." in sdk_manifest_rel.parts or not sdk_manifest_rel.parts:
            raise ManifestError("manifest.sdk_manifest.path must be relative to --sdk")
        sdk_manifest_unresolved = sdk_root / sdk_manifest_rel
        reject_symlink_components(sdk_manifest_unresolved, "SDK manifest")
        sdk_manifest_path = sdk_manifest_unresolved.resolve()
        try:
            sdk_manifest_path.relative_to(sdk_root)
        except ValueError as exc:
            raise ManifestError("SDK manifest escapes --sdk") from exc
        report["inputs"]["sdk_manifest_sha256"] = checked_hash(
            sdk_manifest_path, str(sdk_binding.get("sha256", "")), "SDK manifest"
        )

        compiler = manifest.get("compiler")
        if not isinstance(compiler, dict) or not compiler.get("path"):
            raise ManifestError("manifest.compiler.path must name the actual cross compiler")
        raw_compiler_path = Path(str(compiler["path"])).expanduser()
        reject_symlink_components(raw_compiler_path, "compiler")
        compiler_path = raw_compiler_path.resolve()
        report["inputs"]["compiler"] = {
            "path": str(compiler_path),
            "sha256": checked_hash(compiler_path, str(compiler.get("sha256", "")), "compiler"),
            "target": compiler.get("target"),
        }

        runtime_kind = manifest.get("runtime_kind")
        if runtime_kind != "target_application_runtime":
            for name in selected:
                report["features"][name] = {
                    "status": "not_ready",
                    "reason": f"runtime_kind={runtime_kind!r} is not a target application runtime",
                }
            report["status"] = "not_ready"
            output_root.mkdir(parents=True, exist_ok=True)
            write_report(output_root, report)
            print(f"NOT_READY report={output_root / 'cpp_abi_build_report.json'}")
            return 2

        dumpmachine = [str(compiler_path), "-dumpmachine"]
        try:
            machine_result = subprocess.run(dumpmachine, text=True, stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE, check=False)
        except OSError as exc:
            report["commands"].append({"phase": "compiler_target_check", "command": dumpmachine,
                                       "returncode": None, "stdout": "", "stderr": str(exc)})
            report["status"] = "failed"
            report["error"] = f"cannot run compiler target check: {exc}"
            write_report(output_root, report)
            print(f"FAILED report={output_root / 'cpp_abi_build_report.json'}")
            return 1
        machine_record = {"phase": "compiler_target_check", "command": dumpmachine,
                          "display": shlex.join(dumpmachine), "returncode": machine_result.returncode,
                          "stdout": machine_result.stdout, "stderr": machine_result.stderr}
        report["commands"].append(machine_record)
        if machine_result.returncode != 0:
            report["status"] = "failed"
            report["error"] = "compiler -dumpmachine returned nonzero"
            write_report(output_root, report)
            print(f"FAILED report={output_root / 'cpp_abi_build_report.json'}")
            return 1
        actual_target = machine_result.stdout.strip()
        expected_target = str(manifest.get("target_triple", compiler.get("target", "")))
        report["inputs"]["compiler"]["dumpmachine"] = actual_target
        if actual_target != expected_target or str(compiler.get("target", actual_target)) != expected_target:
            report["status"] = "failed"
            report["error"] = (f"compiler target mismatch: dumpmachine={actual_target!r}, "
                               f"manifest target={expected_target!r}, compiler target={compiler.get('target')!r}")
            write_report(output_root, report)
            print(f"FAILED report={output_root / 'cpp_abi_build_report.json'}")
            return 1

        declarations = manifest.get("features")
        if not isinstance(declarations, dict):
            raise ManifestError("manifest.features must map feature names to status declarations")
        host_flags = parse_string_list(manifest.get("host_library_build_flags"), "host_library_build_flags")
        runtime_flags = parse_string_list(manifest.get("runtime_build_flags"), "runtime_build_flags")
        library_flags = host_flags + runtime_flags
        common_compile = parse_string_list(manifest.get("compile_flags"), "compile_flags")
        common_link = parse_string_list(manifest.get("link_flags"), "link_flags")
        feature_flags = manifest.get("feature_flags", {})
        if not isinstance(feature_flags, dict):
            raise ManifestError("feature_flags must be an object")

        include_args: list[str] = []
        for index, entry in enumerate(manifest.get("include_dirs", [])):
            include_path, digest = resolve_artifact(entry, sdk_root, runtime_root, f"include_dirs[{index}]")
            if not include_path.is_dir():
                raise ManifestError(f"include_dirs[{index}] is not a directory")
            include_args += ["-I", str(include_path)]
            report["artifacts"].append({"role": "include_dir", "path": str(include_path), "sha256": digest})

        crt_path, crt_hash = resolve_artifact(manifest.get("crt"), sdk_root, runtime_root, "crt")
        linker_path, linker_hash = resolve_artifact(manifest.get("linker_script"), sdk_root, runtime_root, "linker_script")
        archive_paths: list[Path] = []
        for index, entry in enumerate(manifest.get("archives", [])):
            path, digest = resolve_artifact(entry, sdk_root, runtime_root, f"archives[{index}]")
            archive_paths.append(path)
            report["artifacts"].append({"role": entry.get("role", "archive"), "path": str(path), "sha256": digest})
        report["artifacts"].extend([
            {"role": "crt", "path": str(crt_path), "sha256": crt_hash},
            {"role": "linker_script", "path": str(linker_path), "sha256": linker_hash},
        ])

        not_ready: dict[str, str] = {}
        for name in selected:
            declaration = declarations.get(name)
            if not isinstance(declaration, dict) or declaration.get("status") != "ready":
                not_ready[name] = "feature declaration is absent or not ready"
                continue
            if name == "exceptions" and any(flag == "-fno-exceptions" for flag in library_flags):
                not_ready[name] = "runtime libraries were built with -fno-exceptions"
            if name == "rtti" and any(flag == "-fno-rtti" for flag in library_flags):
                not_ready[name] = "runtime libraries were built with -fno-rtti"

        for name, reason in not_ready.items():
            report["features"][name] = {"status": "not_ready", "reason": reason}
        ready = [name for name in selected if name not in not_ready]
        if not ready:
            report["status"] = "not_ready"
            write_report(output_root, report)
            print(f"NOT_READY report={output_root / 'cpp_abi_build_report.json'}")
            return 2

        output_root.mkdir(parents=True, exist_ok=True)
        source_hashes: dict[str, str] = {}
        for source in sorted(FIXTURE_ROOT.glob("*")):
            if source.is_file():
                source_hashes[source.name] = sha256_file(source)
        report["inputs"]["fixture_sha256"] = source_hashes

        build_failed = False
        for feature in ready:
            req_feature, source_names = FEATURES[feature]
            feature_entry = declarations[req_feature]
            feature_specific = parse_string_list(feature_flags.get(feature), f"feature_flags.{feature}")
            feature_dir = output_root / feature
            feature_dir.mkdir(parents=True, exist_ok=True)
            objects: list[Path] = []
            for source_name in source_names:
                source_path = FIXTURE_ROOT / source_name
                object_path = feature_dir / (source_path.stem + ".o")
                command = [str(compiler_path), *common_compile, *feature_specific, *include_args,
                           "-c", str(source_path), "-o", str(object_path)]
                try:
                    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
                except OSError as exc:
                    report["commands"].append({"feature": feature, "phase": "compile", "command": command,
                                                "display": shlex.join(command), "returncode": None,
                                                "stdout": "", "stderr": str(exc)})
                    report["features"][feature] = {"status": "failed", "phase": "compile", "error": str(exc)}
                    build_failed = True
                    break
                record = {"feature": feature, "phase": "compile", "command": command,
                          "display": shlex.join(command), "returncode": result.returncode,
                          "stdout": result.stdout, "stderr": result.stderr}
                report["commands"].append(record)
                if result.returncode != 0:
                    report["features"][feature] = {"status": "failed", "phase": "compile", "returncode": result.returncode}
                    build_failed = True
                    break
                objects.append(object_path)
            if build_failed:
                break
            elf_path = feature_dir / f"cpp_abi_{feature}.elf"
            command = [str(compiler_path), *common_link, *feature_specific,
                       "-Wl,-T," + str(linker_path), str(crt_path), *(str(path) for path in objects),
                       "-Wl,--start-group", *(str(path) for path in archive_paths),
                       "-Wl,--end-group", "-o", str(elf_path)]
            try:
                result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            except OSError as exc:
                report["commands"].append({"feature": feature, "phase": "link", "command": command,
                                            "display": shlex.join(command), "returncode": None,
                                            "stdout": "", "stderr": str(exc)})
                report["features"][feature] = {"status": "failed", "phase": "link", "error": str(exc)}
                build_failed = True
                break
            report["commands"].append({"feature": feature, "phase": "link", "command": command,
                                       "display": shlex.join(command), "returncode": result.returncode,
                                       "stdout": result.stdout, "stderr": result.stderr})
            if result.returncode != 0:
                report["features"][feature] = {"status": "failed", "phase": "link", "returncode": result.returncode}
                build_failed = True
                break
            report["features"][feature] = {
                "status": "built_not_run",
                "declaration_evidence": feature_entry.get("evidence"),
                "elf": str(elf_path),
                "sha256": sha256_file(elf_path),
            }
        if build_failed:
            report["status"] = "failed"
            write_report(output_root, report)
            print(f"FAILED report={output_root / 'cpp_abi_build_report.json'}")
            return 1
        report["status"] = "built_not_run" if all(report["features"][name]["status"] == "built_not_run" for name in ready) else "partial_not_ready"
        write_report(output_root, report)
        print(f"{report['status'].upper()} report={output_root / 'cpp_abi_build_report.json'}")
        return 0 if report["status"] == "built_not_run" else 2
    except (ManifestError, OSError, KeyError, TypeError, ValueError) as exc:
        report["status"] = "not_ready"
        report["error"] = str(exc)
        try:
            write_report(output_root, report)
        except OSError:
            pass
        print(f"NOT_READY: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
