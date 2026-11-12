# SPDX-License-Identifier: Apache-2.0
"""Check scripts/ports.py accepts the shipped tree and rejects each broken field."""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts/ports.py"
README = """# example_port

## 状态

`planned`。

## 构建

（配方待补。）

## 安装与验证

（待补。）

## 已知限制

（待补。）
"""


def run(*arguments):
    return subprocess.run([sys.executable, str(VALIDATOR), *arguments],
                          capture_output=True, text=True)


def base_port(directory, **overrides):
    port = {
        "format_version": 1,
        "id": directory.name,
        "name": "Example Port",
        "upstream_version": "1.0.0",
        "license": ["MIT"],
        "homepage": None,
        "source": None,
        "build": {"system": "custom", "recipe": None, "patches": []},
        "package": {"id": "example.port", "target_profile": "xos-x86_64-static-single-b2-v1",
                    "xpk_sha256": None},
        "integration": {"guest_only": True, "bootstrap_images": [], "iso_members": []},
        "status": "planned",
        "note": "fixture",
        "evidence": [],
    }
    port.update(overrides)
    (directory / "port.json").write_text(json.dumps(port, indent=2) + "\n")
    (directory / "README.md").write_text(README)
    return port


def main():
    results = []

    def check(name, condition, detail=""):
        results.append({"name": name, "ok": bool(condition), "detail": detail})
        print(("PASS " if condition else "FAIL ") + name + (f" :: {detail}" if detail and not condition else ""))

    everything = run("check", "--all", "--json")
    payload = json.loads(everything.stdout)
    check("shipped tree passes", everything.returncode == 0 and payload["status"] == "passed",
          everything.stdout + everything.stderr)
    check("nasm is discovered", "src/ports/nasm" in payload["checked"], str(payload["checked"]))

    template = run("check", "src/ports/_template")
    check("template directories are refused explicitly",
          template.returncode == 1 and "not validated" in template.stdout, template.stdout)

    scratch = Path(tempfile.mkdtemp(prefix="ports_check_"))
    try:
        cases = []

        def case(name, expected, mutate):
            directory = scratch / name
            directory.mkdir()
            port = base_port(directory)
            mutate(directory, port)
            result = run("check", str(directory))
            cases.append((name, expected, result))

        case("unknown_field", "unknown fields", lambda d, p: base_port(d, extra=1))
        case("bad_status", "expected one of", lambda d, p: base_port(d, status="done"))
        case("bad_profile", "no config/package profile", lambda d, p: base_port(
            d, package={"id": "example.port", "target_profile": "nope", "xpk_sha256": None}))
        case("bad_hash", "64 lowercase hex", lambda d, p: base_port(
            d, package={"id": "example.port",
                        "target_profile": "xos-x86_64-static-single-b2-v1",
                        "xpk_sha256": "abc"}))
        case("guest_only_members", "guest-only ports must not", lambda d, p: base_port(
            d, integration={"guest_only": True, "bootstrap_images": ["supervisor"],
                            "iso_members": []}))
        case("missing_recipe", "requires", lambda d, p: base_port(d, status="guest_verified"))
        case("missing_evidence", "requires evidence", lambda d, p: base_port(
            d, status="cross_built_guest_not_run"))
        case("bad_evidence_path", "evidence file is missing", lambda d, p: base_port(
            d, status="cross_built_guest_not_run", evidence=["docs/does_not_exist.md"]))
        case("readme_sections", "missing", lambda d, p: (d / "README.md").write_text("# only\n"))

        def patch_case(directory, port):
            patches = directory / "patches"
            patches.mkdir()
            (patches / "0001_thing.patch").write_text("not a git patch\n")
            base_port(directory, status="source_locked",
                      build={"system": "custom", "recipe": None,
                             "patches": ["patches/0001_thing.patch"]})

        case("patch_format", "git format-patch", patch_case)

        def write_lock(directory):
            (directory / "source_lock.json").write_text(json.dumps({
                "kind": "tarball", "version": "1.0.0",
                "url": "https://example.invalid/tool-1.0.0.tar.gz",
                "archive": "tool-1.0.0.tar.gz", "sha256": "a" * 64}, indent=2) + "\n")

        def locked(directory, status="source_locked"):
            write_lock(directory)
            return dict(source={"kind": "tarball", "lock": "source_lock.json"}, status=status)

        def source_locked_without_source(directory, port):
            base_port(directory, status="source_locked")

        case("source_locked_without_source", "requires a locked upstream source",
             source_locked_without_source)

        def non_object_port(directory, port):
            (directory / "port.json").write_text("[]\n")

        case("non_object_port", "expected an object", non_object_port)

        def non_object_lock(directory, port):
            base_port(directory, **locked(directory))
            (directory / "source_lock.json").write_text("[]\n")

        case("non_object_lock", "expected an object", non_object_lock)

        def null_port(directory, port):
            (directory / "port.json").write_text("null\n")

        case("null_port", "expected an object", null_port)

        def null_lock(directory, port):
            base_port(directory, **locked(directory))
            (directory / "source_lock.json").write_text("null\n")

        case("null_lock", "expected an object", null_lock)

        def patch_gap(directory, port):
            patches = directory / "patches"
            patches.mkdir()
            (patches / "0002_thing.patch").write_text(
                "From " + "a" * 40 + " Mon Sep 17 00:00:00 2001\nSubject: [PATCH] t\n")
            base_port(directory, build={"system": "custom", "recipe": None,
                                        "patches": ["patches/0002_thing.patch"]})

        case("patch_gap", "consecutive", patch_gap)

        def patch_binary(directory, port):
            patches = directory / "patches"
            patches.mkdir()
            (patches / "0001_thing.patch").write_text(
                "From " + "a" * 40 + " Mon Sep 17 00:00:00 2001\nSubject: [PATCH] t\n\n"
                "diff --git a/x b/x\nindex 1111111..2222222 100644\n"
                "GIT binary patch\nliteral 3\n")
            base_port(directory, build={"system": "custom", "recipe": None,
                                        "patches": ["patches/0001_thing.patch"]})

        case("patch_binary", "forbidden patch operation", patch_binary)

        def patch_mode(directory, port):
            patches = directory / "patches"
            patches.mkdir()
            (patches / "0001_thing.patch").write_text(
                "From " + "a" * 40 + " Mon Sep 17 00:00:00 2001\nSubject: [PATCH] t\n\n"
                "diff --git a/x b/x\nold mode 100644\nnew mode 100755\n")
            base_port(directory, build={"system": "custom", "recipe": None,
                                        "patches": ["patches/0001_thing.patch"]})

        case("patch_mode", "forbidden patch operation", patch_mode)

        def empty_license(directory, port):
            base_port(directory, license=[])

        case("empty_license", "at least one license", empty_license)

        case("status_type", "expected one of", lambda d, p: base_port(d, status=[]))

        def good_patch(directory, port):
            patches = directory / "patches"
            patches.mkdir()
            (patches / "0001_thing.patch").write_text(
                "From " + "a" * 40 + " Mon Sep 17 00:00:00 2001\n"
                "Subject: [PATCH] thing\n\n---\n a | 1 +\n")
            base_port(directory, **locked(directory),
                      build={"system": "custom", "recipe": None,
                             "patches": ["patches/0001_thing.patch"]})

        def text_mentions_binary(directory, port):
            patches = directory / "patches"
            patches.mkdir()
            (patches / "0001_thing.patch").write_text(
                "From " + "a" * 40 + " Mon Sep 17 00:00:00 2001\n"
                "Subject: [PATCH] mention GIT binary patch in prose\n\n"
                "GIT binary patch is a marker we mention in the commit message\n"
                "---\n x.c | 1 +\n\n"
                "diff --git a/x.c b/x.c\n--- a/x.c\n+++ b/x.c\n"
                "@@ -0,0 +1 @@\n+puts(\"GIT binary patch\");\n")
            base_port(directory, **locked(directory),
                      build={"system": "custom", "recipe": None,
                             "patches": ["patches/0001_thing.patch"]})

        directory = scratch / "text_mentions_binary"
        directory.mkdir()
        text_mentions_binary(directory, base_port(directory))
        result = run("check", str(directory))
        check("prose mentioning binary markers accepted",
              result.returncode == 0, result.stdout + result.stderr)

        directory = scratch / "good_patch"
        directory.mkdir()
        good_patch(directory, base_port(directory))
        result = run("check", str(directory))
        check("valid git patch accepted", result.returncode == 0, result.stdout + result.stderr)

        for name, expected, result in cases:
            passed = result.returncode == 1 and expected in result.stdout
            check(name, passed, f"exit={result.returncode} stdout={result.stdout} stderr={result.stderr}")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    report = {"status": "passed" if all(item["ok"] for item in results) else "failed",
              "checks": results}
    (ROOT / "build").mkdir(exist_ok=True)
    (ROOT / "build/ports_manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "checks": len(results),
                      "failed": [item["name"] for item in results if not item["ok"]]}, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
