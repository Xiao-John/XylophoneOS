#!/usr/bin/env python3
"""Validate src/ports/<id>/port.json against docs/ports.md (structure only)."""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORTS = ROOT / "src/ports"

ID = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
PACKAGE_ID = re.compile(r"^[a-z][a-z0-9_]*(?:[.-][a-z0-9_]+)*$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
PATCH = re.compile(r"^(\d{4})_[a-z0-9_]+\.patch$")
STATUS = {
    "planned", "source_locked", "cross_built_guest_not_run",
    "packed_guest_not_run", "guest_verified", "blocked", "retired",
}
SYSTEMS = {"autotools", "make", "cmake", "meson", "custom", "prebuilt"}
SOURCES = {"tarball", "git", "component_set"}
BUILT = {"cross_built_guest_not_run", "packed_guest_not_run", "guest_verified"}
PACKED = {"packed_guest_not_run", "guest_verified"}
README_SECTIONS = ("状态", "构建", "安装与验证", "已知限制")
PORT_FIELDS = {"format_version", "id", "name", "upstream_version", "license", "homepage",
               "source", "build", "package", "integration", "status", "note", "evidence"}
BUILD_FIELDS = {"system", "recipe", "patches"}
PACKAGE_FIELDS = {"id", "target_profile", "xpk_sha256"}
INTEGRATION_FIELDS = {"guest_only", "bootstrap_images", "iso_members"}


def rel(path):
    try:
        return str(Path(path).relative_to(ROOT))
    except ValueError:
        return str(path)


class Report:
    def __init__(self):
        self.errors = []
        self.checked = []

    def fail(self, where, message):
        self.errors.append(f"{where}: {message}")


def text(value, where, report, low=1, high=512):
    if not isinstance(value, str) or not (low <= len(value) <= high):
        report.fail(where, f"expected string of {low}..{high} bytes")
        return False
    return True


def string_list(value, where, report, limit=256):
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        report.fail(where, "expected non-empty string array")
        return False
    if len(value) > limit:
        report.fail(where, f"at most {limit} entries")
        return False
    return True


def inside(base, relative, where, report):
    path = (base / relative).resolve()
    try:
        path.relative_to(base.resolve())
    except ValueError:
        report.fail(where, "path escapes the port directory")
        return None
    return path


def load(path, where, report):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        report.fail(where, "file is missing")
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        report.fail(where, f"unreadable JSON: {error}")
    return None


def check_tarball(lock, where, report):
    for name in ("version", "url", "archive"):
        if not text(lock.get(name), f"{where}.{name}", report, 1, 1024):
            continue
    if not isinstance(lock.get("sha256"), str) or not HEX64.fullmatch(lock["sha256"]):
        report.fail(where + ".sha256", "expected 64 lowercase hex characters")
    if not isinstance(lock.get("url"), str) or not lock.get("url", "").startswith(
            ("https://", "http://", "git+", "file:")):
        report.fail(where + ".url", "expected an absolute source URL")


def check_git(lock, where, report):
    if not text(lock.get("repository"), f"{where}.repository", report, 1, 1024):
        return
    commit = lock.get("commit")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        report.fail(where + ".commit", "expected a 40-character lowercase commit id")
    text(lock.get("tree"), f"{where}.tree", report, 1, 1024)
    files = lock.get("files")
    if not isinstance(files, list):
        report.fail(where + ".files", "expected an array")
        return
    for index, item in enumerate(files):
        entry = f"{where}.files[{index}]"
        if not isinstance(item, dict):
            report.fail(entry, "expected an object")
            continue
        text(item.get("path"), entry + ".path", report, 1, 512)
        if not isinstance(item.get("sha256"), str) or not HEX64.fullmatch(item["sha256"]):
            report.fail(entry + ".sha256", "expected 64 lowercase hex characters")


def check_components(lock, where, report):
    components = lock.get("components")
    if not isinstance(components, list) or not components:
        report.fail(where + ".components", "expected a non-empty array")
        return
    for index, item in enumerate(components):
        entry = f"{where}.components[{index}]"
        if not isinstance(item, dict):
            report.fail(entry, "expected an object")
            continue
        for name in ("name", "version", "url", "license"):
            text(item.get(name), f"{entry}.{name}", report, 1, 1024)
        if not isinstance(item.get("sha256"), str) or not HEX64.fullmatch(item["sha256"]):
            report.fail(entry + ".sha256", "expected 64 lowercase hex characters")


SOURCE_CHECKS = {"tarball": check_tarball, "git": check_git, "component_set": check_components}


def check_source(port, base, where, report):
    source = port.get("source")
    if source is None:
        return
    if not isinstance(source, dict):
        report.fail(where + ".source", "expected null or an object")
        return
    unknown = set(source) - {"kind", "lock"}
    if unknown:
        report.fail(where + ".source", f"unknown fields: {sorted(unknown)}")
    kind = source.get("kind")
    if kind not in SOURCES:
        report.fail(where + ".source.kind", f"expected one of {sorted(SOURCES)}")
        return
    lock_name = source.get("lock", "source_lock.json")
    if not text(lock_name, where + ".source.lock", report, 1, 256):
        return
    lock_path = inside(base, lock_name, where + ".source.lock", report)
    if lock_path is None:
        return
    lock = load(lock_path, rel(lock_path), report)
    if not isinstance(lock, dict):
        return
    if lock.get("kind") != kind:
        report.fail(rel(lock_path) + ".kind",
                    f"must equal source.kind {kind!r}")
    SOURCE_CHECKS[kind](lock, rel(lock_path), report)


def check_patches(port, base, where, report):
    build = port.get("build")
    patches = build.get("patches", [])
    if not string_list(patches, where + ".build.patches", report):
        return
    listed = set()
    previous = 0
    for index, name in enumerate(patches):
        entry = f"{where}.build.patches[{index}]"
        match = PATCH.fullmatch(Path(name).name)
        if not match or Path(name).parent.as_posix() != "patches":
            report.fail(entry, "expected patches/NNNN_topic.patch")
            continue
        number = int(match.group(1))
        if number <= previous:
            report.fail(entry, "sequence numbers must increase from 0001")
        previous = number
        path = inside(base, name, entry, report)
        if path is None:
            continue
        if not path.is_file():
            report.fail(entry, "patch file is missing")
            continue
        listed.add(Path(name).name)
        head = path.read_text(errors="replace").splitlines()
        if not head or not re.fullmatch(r"From [0-9a-f]{40} .+", head[0]):
            report.fail(entry, "not a git format-patch file (missing 'From <commit> ...')")
        if not any(line.startswith("Subject:") for line in head[:20]):
            report.fail(entry, "not a git format-patch file (missing Subject:)")
    directory = base / "patches"
    if directory.is_dir():
        actual = sorted(p.name for p in directory.glob("*.patch"))
        unlisted = [name for name in actual if name not in listed]
        if unlisted:
            report.fail(where + ".build.patches", f"unlisted patch files: {unlisted}")


def check_recipe(port, base, where, report, status):
    recipe = port.get("build", {}).get("recipe")
    if status in BUILT:
        if not text(recipe, where + ".build.recipe", report, 1, 256):
            return
        path = inside(base, recipe, where + ".build.recipe", report)
        if path is not None and not path.is_file():
            report.fail(where + ".build.recipe", "recipe file is missing")
    elif recipe is not None:
        inside(base, recipe, where + ".build.recipe", report)


def check_evidence(port, where, report, status):
    evidence = port.get("evidence", [])
    if not string_list(evidence, where + ".evidence", report):
        return
    if status in BUILT and not evidence:
        report.fail(where + ".evidence", f"status {status!r} requires evidence")
    for index, relative in enumerate(evidence):
        entry = f"{where}.evidence[{index}]"
        path = (ROOT / relative).resolve()
        try:
            path.relative_to(ROOT)
        except ValueError:
            report.fail(entry, "path escapes the repository")
            continue
        if not path.is_file():
            report.fail(entry, "evidence file is missing")


def check_readme(base, where, report):
    path = base / "README.md"
    if not path.is_file():
        report.fail(where, "README.md is missing")
        return
    headings = [line for line in path.read_text(errors="replace").splitlines()
                if line.startswith("##")]
    for section in README_SECTIONS:
        if not any(section in line for line in headings):
            report.fail(rel(path), f"missing '## {section}' section")


def check_port(directory, report, profiles, seen, package_seen):
    where = rel(directory)
    port = load(directory / "port.json", where + "/port.json", report)
    if not isinstance(port, dict):
        return
    unknown = set(port) - PORT_FIELDS
    if unknown:
        report.fail(where + "/port.json", f"unknown fields: {sorted(unknown)}")
        return
    if port.get("format_version") != 1:
        report.fail(where + "/port.json.format_version", "must be 1")
    identifier = port.get("id")
    if not isinstance(identifier, str) or not ID.fullmatch(identifier):
        report.fail(where + "/port.json.id", "expected lowercase identifier")
    elif identifier != directory.name:
        report.fail(where + "/port.json.id", "must equal the directory name")
    elif identifier in seen:
        report.fail(where + "/port.json.id", f"duplicate port id {identifier!r}")
    else:
        seen.add(identifier)
    text(port.get("name"), where + "/port.json.name", report, 1, 120)
    text(port.get("upstream_version"), where + "/port.json.upstream_version", report, 1, 128)
    if not string_list(port.get("license"), where + "/port.json.license", report, 16):
        pass
    homepage = port.get("homepage")
    if homepage is not None and (not isinstance(homepage, str) or not homepage.startswith("https://")):
        report.fail(where + "/port.json.homepage", "expected https:// URL or null")
    status = port.get("status")
    if status not in STATUS:
        report.fail(where + "/port.json.status", f"expected one of {sorted(STATUS)}")
        return
    text(port.get("note"), where + "/port.json.note", report, 1, 512)
    if status == "blocked" and len(port.get("note", "")) < 10:
        report.fail(where + "/port.json.note", "blocked ports must describe the blocker")

    check_source(port, directory, where + "/port.json", report)

    build = port.get("build")
    if not isinstance(build, dict):
        report.fail(where + "/port.json.build", "expected an object")
    else:
        if set(build) - BUILD_FIELDS:
            report.fail(where + "/port.json.build", f"unknown fields: {sorted(set(build) - BUILD_FIELDS)}")
        if build.get("system") not in SYSTEMS:
            report.fail(where + "/port.json.build.system", f"expected one of {sorted(SYSTEMS)}")
        check_patches(port, directory, where + "/port.json", report)
        check_recipe(port, directory, where, report, status)

    package = port.get("package")
    if not isinstance(package, dict):
        report.fail(where + "/port.json.package", "expected an object")
    else:
        if set(package) - PACKAGE_FIELDS:
            report.fail(where + "/port.json.package", f"unknown fields: {sorted(set(package) - PACKAGE_FIELDS)}")
        package_id = package.get("id")
        if not isinstance(package_id, str) or not PACKAGE_ID.fullmatch(package_id):
            report.fail(where + "/port.json.package.id", "expected package identifier")
        elif package_id in package_seen:
            report.fail(where + "/port.json.package.id", f"duplicate package id {package_id!r}")
        else:
            package_seen.add(package_id)
        profile = package.get("target_profile")
        if profile not in profiles:
            report.fail(where + "/port.json.package.target_profile",
                        f"no config/package profile declares id {profile!r}")
        digest = package.get("xpk_sha256")
        if digest is None:
            if status in PACKED:
                report.fail(where + "/port.json.package.xpk_sha256",
                            f"status {status!r} requires the packed artifact hash")
        elif not isinstance(digest, str) or not HEX64.fullmatch(digest):
            report.fail(where + "/port.json.package.xpk_sha256", "expected 64 lowercase hex characters")

    integration = port.get("integration")
    if not isinstance(integration, dict):
        report.fail(where + "/port.json.integration", "expected an object")
    else:
        if set(integration) - INTEGRATION_FIELDS:
            report.fail(where + "/port.json.integration",
                        f"unknown fields: {sorted(set(integration) - INTEGRATION_FIELDS)}")
        if not isinstance(integration.get("guest_only"), bool):
            report.fail(where + "/port.json.integration.guest_only", "expected a boolean")
        for name in ("bootstrap_images", "iso_members"):
            if not string_list(integration.get(name), f"{where}/port.json.integration.{name}", report):
                continue
            if integration.get("guest_only") and integration[name]:
                report.fail(f"{where}/port.json.integration.{name}",
                            "guest-only ports must not add boot or ISO members")

    check_evidence(port, where + "/port.json", report, status)
    check_readme(directory, where, report)


def profile_ids():
    ids = set()
    for path in sorted((ROOT / "config/package").glob("*.json")):
        try:
            value = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict) and isinstance(value.get("id"), str):
            ids.add(value["id"])
    return ids


def discover():
    paths = []
    for entry in sorted(PORTS.iterdir()):
        if entry.is_dir() and not entry.name.startswith("_") and (entry / "port.json").is_file():
            paths.append(entry)
    return paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("check", nargs="?")
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--all", action="store_true", help="check every directory with port.json")
    parser.add_argument("--json", action="store_true", help="machine-readable summary")
    args = parser.parse_args()
    if args.check not in (None, "check"):
        parser.error("only the 'check' subcommand is implemented")
    if args.all:
        targets = discover()
    elif args.paths:
        targets = [p if p.is_absolute() else (ROOT / p) for p in args.paths]
    else:
        parser.error("give a port directory, or --all")
    report = Report()
    profiles = profile_ids()
    seen, package_seen = set(), set()
    for target in targets:
        if not target.is_dir():
            report.fail(str(target), "not a directory")
            continue
        if target.name.startswith("_"):
            report.fail(rel(target), "template/draft directory is not validated; copy it to src/ports/<id> first")
            continue
        if not (target / "port.json").is_file():
            report.fail(rel(target), "port.json is missing; this directory is not under the spec")
            continue
        report.checked.append(rel(target))
        check_port(target, report, profiles, seen, package_seen)
    if args.json:
        print(json.dumps({"checked": report.checked, "errors": report.errors,
                          "status": "failed" if report.errors else "passed"}, indent=2))
    else:
        for line in report.errors:
            print(line)
        print(f"ports: {len(report.checked)} checked, {len(report.errors)} error(s)")
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
