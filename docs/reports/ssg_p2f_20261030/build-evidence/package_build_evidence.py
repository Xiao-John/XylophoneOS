#!/usr/bin/env python3
"""Copy existing build evidence into this directory; never build or run guests."""
from pathlib import Path
import datetime
import gzip
import hashlib
import io
import json
import os
import sys
import re
import shlex
import subprocess
import tarfile
import urllib.parse

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
assert (ROOT / "config/toolchain.json").is_file()
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]
from ssg_public_paths import portable
from check_public_evidence_paths import scan, Budget
PUBLIC_MAPPINGS = [(name, os.environ.get(name)) for name in (
    "XOS_SDK_PREFIX", "XOS_BUILD_DIR", "XOS_QT_SOURCE", "XOS_HOST_QT",
    "XOS_BINUTILS", "XOS_BASE_ROOT", "XOS_WORKSPACE", "XOS_TOOLCHAIN_PREFIX",
    "XOS_HOST_HOME", "XOS_CODEX_RUNTIME", "XOS_PYTHON_FRAMEWORK", "XOS_PREVIOUS_ROOT")]
PUBLIC_MAPPINGS.append(("XOS_PYTHON", sys.executable))

def safe_public_bytes(data, name):
    findings = []
    scan(data, name, findings, expected=name,
         budget=Budget([os.environ.get("XOS_PRIVATE_IDENTITY", Path.home().name)]))
    if findings:
        raise RuntimeError("Public evidence requires review: " + name + " " +
                           ",".join(sorted({row["category"] for row in findings})))
    return data

def shell_template(value):
    parts = re.split(r'(\$\{XOS_[A-Z0-9_]+\})', str(value))
    if len(parts) == 1:
        return shlex.quote(str(value))
    pieces = []
    for part in parts:
        if re.fullmatch(r'\$\{XOS_[A-Z0-9_]+\}', part):
            pieces.append(part)
        else:
            pieces.append(''.join((chr(92) if c in (chr(92), chr(34), chr(96), chr(36)) else '') + c for c in part))
    return '"' + ''.join(pieces) + '"'
sha = lambda data: hashlib.sha256(data).hexdigest()
read_json = lambda name: json.loads((ROOT / name).read_text())
def write_json(name, value):
    value = portable(value, PUBLIC_MAPPINGS, strict=True)
    data = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()
    (OUT / name).write_bytes(safe_public_bytes(data, name))

selected = set()
def add(name):
    path = ROOT / name
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("Missing regular evidence file: " + name)
    selected.add(name)

for base in (".cache/ssg_p2f/logs", "build/threading_sdk_logs"):
    for path in (ROOT / base).rglob("*"):
        if path.is_file() and path.suffix in (".json", ".log", ".txt", ".html"):
            add(str(path.relative_to(ROOT)))
for path in (ROOT / ".cache/ssg_p2f/downloads").iterdir():
    if path.is_file() and path.suffix in (".json", ".xml", ".sha1", ".sha256"):
        add(str(path.relative_to(ROOT)))
for base in ("build/ssg_p2f/payloads", "build/ssg_p2f/oracle-browser"):
    for path in (ROOT / base).rglob("*"):
        if path.is_file() and (path.name.endswith(".receipt.json") or path.name == "manifest.json" or path.suffix == ".log"):
            add(str(path.relative_to(ROOT)))
for name in (
    ".cache/ssg_p2f/bootstrap_tools.py", ".cache/ssg_p2f/build_runtime.py",
    ".cache/ssg_p2f/build_payloads.py", ".cache/ssg_p2f/env.sh",
    ".cache/ssg_p2f/threading_newlib/receipt.json",
    ".cache/ssg_p2f/threading_newlib/configure.log",
    ".cache/ssg_p2f/threading_newlib/make.log",
    ".cache/ssg_p2f/threading_newlib/install.log",
    ".cache/ssg_p2f/threading_newlib/build/config.log",
    ".cache/ssg_p2f/threading_newlib/build/x86_64-elf/newlib/config.log",
    "build/ssg_p2f/system/manifest.json", "build/ssg_p2f/system/sdk/manifest.json",
    "build/ssg_p2f/system/compiler_configuration.log", "build/ssg_p2f/system/kernel_elf.log",
    "build/ssg_p2f/sdk/manifest.json", "build/ssg_p2f/sdk/compile.py",
    "build/ssg_p2f/qt-widgets/CMakeCache.txt", "build/ssg_p2f/qt-widgets/config.summary",
    "build/ssg_p2f/qt-widgets/build.ninja", "build/ssg_p2f/qt-widgets/CMakeFiles/rules.ninja",
    ".cache/ssg_p2f/build/qemu/build.ninja", ".cache/ssg_p2f/build/qemu/config-host.mak",
    ".cache/ssg_p2f/build/qemu/config.status", ".cache/ssg_p2f/build/qemu/config.log",
    ".cache/ssg_p2f/build/gcc/config.log", ".cache/ssg_p2f/build/binutils/config.log",
    "config/toolchain.json", "src/ports/gcc/source_lock.json",
    "src/ports/binutils/source_lock.json", "src/ports/qt6/source_lock.json",
    "src/ports/aurora_browser/source_lock.json", "scripts/build_threading_newlib.py",
    "scripts/build_threading_sdk.py", "scripts/build_ssg_p1.py", "scripts/build.py",
    "src/ports/qt6/prepare_source.py", "src/ports/qt6/configure_widgets.py",
    "src/ports/qt6/build_fixture.py", "src/ports/qt6/build_widgets_fixture.py",
    "src/ports/aurora_browser/build.py",
):
    add(name)

redactions = []
header = re.compile(r"(?im)^(Authorization|Proxy-Authorization|Cookie|Set-Cookie|x-77-nzt(?:-ray)?):[^\r\n]*")
urls = re.compile(r"https?://[^\s<>\"'\\]+")
secret_query = re.compile(r"(?i)^(?:access_token|auth_token|token|api_key|apikey|key|signature|sig|x-amz-(?:credential|signature|security-token)|x-goog-(?:credential|signature)|se|sp|sv)$")
credential = re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{24,})")

def sanitize(name, data):
    text = data.decode("utf-8")
    changes = []
    def redact_header(match):
        changes.append({"kind": "response_or_auth_header", "field": match.group(1)})
        return match.group(1) + ": [REDACTED]"
    text = header.sub(redact_header, text)
    def redact_url(match):
        original = match.group(0)
        parsed = urllib.parse.urlsplit(original)
        pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        changed = False
        host = parsed.netloc
        if "@" in host:
            host = "REDACTED@" + host.rsplit("@", 1)[1]
            changes.append({"kind": "url_userinfo"})
            changed = True
        clean_pairs = []
        for key, value in pairs:
            if secret_query.match(key):
                clean_pairs.append((key, "REDACTED"))
                changes.append({"kind": "credential_url_parameter", "field": key})
                changed = True
            else:
                clean_pairs.append((key, value))
        return urllib.parse.urlunsplit((parsed.scheme, host, parsed.path, urllib.parse.urlencode(clean_pairs), parsed.fragment)) if changed else original
    text = urls.sub(redact_url, text)
    def redact_token(match):
        changes.append({"kind": "credential_token_pattern"})
        return "[REDACTED_TOKEN]"
    text = credential.sub(redact_token, text)
    if "-----BEGIN PRIVATE KEY-----" in text or "-----BEGIN RSA PRIVATE KEY-----" in text:
        raise RuntimeError("Private key marker in evidence: " + name)
    public_text = portable(text, PUBLIC_MAPPINGS, strict=True)
    if public_text != text:
        changes.append({"kind": "path_template"})
    result = safe_public_bytes(public_text.encode("utf-8"), name)
    if changes:
        redactions.append({"path": name, "changes": changes,
                           "original_sha256": sha(data), "exported_sha256": sha(result)})
    return result

payload = read_json(".cache/ssg_p2f/logs/payloads-build.json")
verified = read_json(".cache/ssg_p2f/logs/payloads-verified.json")
manifest = read_json("build/ssg_p2f/payloads/manifest.json")
system = read_json("build/ssg_p2f/system/manifest.json")
environment = read_json(".cache/ssg_p2f/logs/current-environment.json")
runtime = read_json(".cache/ssg_p2f/logs/runtime-build.json")
inputs = read_json(".cache/ssg_p2f/logs/bootstrap-inputs.json")
commit = payload["source_commit"]
tree = subprocess.check_output(["git", "rev-parse", commit + "^{tree}"], cwd=ROOT, text=True).strip()
head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()

artifact_check = {}
for path, expected in payload["artifacts"].items():
    actual = sha((ROOT / path).read_bytes())
    assert actual == expected, path
    artifact_check[path] = {"sha256": actual, "bytes": (ROOT / path).stat().st_size}
browser_checks = {}
for path, oracle in (("build/ssg_p2f/payloads/browser/browser.receipt.json", False),
                     ("build/ssg_p2f/oracle-browser/browser.receipt.json", True)):
    receipt = read_json(path)
    assert receipt["test_structure_oracle"] is oracle
    mismatches = [source for source, digest in receipt["inputs"].items() if sha(Path(source).read_bytes()) != digest]
    assert not mismatches, mismatches
    tool_mismatches = [tool for tool, value in receipt["tools"].items() if sha(Path(tool).read_bytes()) != value["sha256"]]
    assert not tool_mismatches, tool_mismatches
    browser_checks[path] = {"test_structure_oracle": oracle, "input_count": len(receipt["inputs"]),
                           "all_inputs_match": True, "all_tools_match": True,
                           "receipt_sha256": sha((ROOT / path).read_bytes()), "elf_sha256": receipt["elf_sha256"]}

session = {
    "record_type": "post_build_summary_derived_from_existing_payload_manifest",
    "not_an_original_standalone_receipt": True,
    "source_commit": commit,
    "original_manifest": "build/ssg_p2f/payloads/manifest.json",
    "original_manifest_sha256": sha((ROOT / "build/ssg_p2f/payloads/manifest.json").read_bytes()),
    "command": manifest["commands"][0],
    "source": "src/user/apps/ssg_session.cpp",
    "source_sha256": manifest["source_sha256"]["src/user/apps/ssg_session.cpp"],
    "sdk_manifest_sha256": manifest["sdk_manifest_sha256"],
    "compile_driver": "build/ssg_p2f/sdk/compile.py",
    "compile_driver_sha256": sha((ROOT / "build/ssg_p2f/sdk/compile.py").read_bytes()),
    "elf": "build/ssg_p2f/payloads/session.elf",
    "elf_sha256": manifest["artifacts"]["session.elf"],
}

records = {}
inventory = []
for name in sorted(selected):
    original = (ROOT / name).read_bytes()
    exported = sanitize(name, original)
    records[name] = exported
    inventory.append({"path": name, "original_bytes": len(original), "exported_bytes": len(exported),
                      "original_sha256": sha(original), "exported_sha256": sha(exported),
                      "byte_identical": original == exported})
session = portable(session, PUBLIC_MAPPINGS, strict=True)
records["derived/session-summary.json"] = (json.dumps(session, indent=2) + "\n").encode()
records["derived/build-job-control.patch"] = subprocess.check_output(
    ["git", "diff", "9a739c7052d66dd75c0a0aceb807b0e4aa2fc16f", commit, "--",
     "scripts/build_threading_newlib.py", "scripts/build_threading_sdk.py"], cwd=ROOT)

command_rows = []
def command(label, argv, cwd, source, returncode=None, provenance="recorded"):
    row = {"label": label, "command": argv, "cwd": cwd, "source": source, "provenance": provenance}
    if returncode is not None:
        row["returncode"] = returncode
    command_rows.append(row)

for row in read_json(".cache/ssg_p2f/logs/bootstrap-tools.json"):
    command(row["label"], row["command"], row["cwd"], ".cache/ssg_p2f/logs/bootstrap-tools.json", row["returncode"])
command("qemu-configure", read_json(".cache/ssg_p2f/logs/qemu-configure-command.json"),
        str(ROOT / ".cache/ssg_p2f/build/qemu"), ".cache/ssg_p2f/logs/qemu-configure-command.json")
for row in read_json(".cache/ssg_p2f/logs/qemu-build-receipt.json"):
    command(row["name"], row["command"], str(ROOT / ".cache/ssg_p2f/build/qemu"),
            ".cache/ssg_p2f/logs/qemu-build-receipt.json", row["returncode"])
row = read_json(".cache/ssg_p2f/logs/qemu-install-retry-receipt.json")
command("qemu-install-after-byte-restoration", row["command"], str(ROOT / ".cache/ssg_p2f/build/qemu"),
        ".cache/ssg_p2f/logs/qemu-install-retry-receipt.json", row["returncode"])
command("qt-source-preparation", ["python3", "src/ports/qt6/prepare_source.py",
        ".cache/ssg_p2f/downloads/qtbase-everywhere-src-6.8.3.tar.xz", ".cache/ssg_p2f/qt-target-source"],
        str(ROOT), ".cache/ssg_p2f/logs/qt-prepare-source.log", provenance="equivalent invocation reconstructed from preserved paths and builder interface")
command("system", ["python3", "scripts/build.py", "--output-dir", "build/ssg_p2f/system"],
        str(ROOT), "build/ssg_p2f/system/manifest.json", provenance="outer invocation retained in build handoff; internal argv arrays in original manifest")
for source in (".cache/ssg_p2f/logs/runtime-build.json", ".cache/ssg_p2f/logs/payloads-build.json"):
    for row in read_json(source)["commands"]:
        command(row["label"], row["command"], str(ROOT), source, row["returncode"])
for i, argv in enumerate(manifest["commands"], 1):
    command("payload-component-" + str(i), argv, str(ROOT), "build/ssg_p2f/payloads/manifest.json")
command_rows = portable(command_rows, PUBLIC_MAPPINGS, strict=True)
records["derived/top-level-commands.json"] = (json.dumps(command_rows, indent=2) + "\n").encode()
for name, data in records.items():
    safe_public_bytes(data, name)

archive = OUT / "build-records.tar.gz"
with archive.open("wb") as destination:
    with gzip.GzipFile(filename="", mode="wb", fileobj=destination, compresslevel=9, mtime=0) as zipped:
        with tarfile.open(fileobj=zipped, mode="w") as tar:
            for name, data in sorted(records.items()):
                member = tarfile.TarInfo(name)
                member.size = len(data)
                member.mode = 0o644
                member.mtime = 0
                tar.addfile(member, io.BytesIO(data))

excluded = [
    {"path": ".cache/ssg_p2f/downloads/qemu-11.1.2.truncated.tar.xz", "reason": "large failed archive; size, SHA256 and failure are preserved in qemu-initial-failure.json"},
    {"path": ".cache/ssg_p2f/logs/qemu-mismatched-source/qemu-11.1.2/pc-bios/edk2-i386-code.fd.bz2", "reason": "binary failed UEFI blob; exact before/after size and hashes are preserved in firmware audit and integrity repair JSON"},
    {"path": "build/ssg_p2f/system/kernel_disassembly.log", "reason": "large generated disassembly; system manifest and kernel ELF metadata are included"},
    {"path": "ELFs, disk images, static archives, downloaded source archives, source/build trees", "reason": "not part of the small text evidence export; identities are recorded by hashes"},
]
write_json("inventory.json", {"archive": archive.name, "original_file_count": len(inventory),
    "records": inventory, "derived_members": [{"path": name, "bytes": len(data), "sha256": sha(data)} for name, data in records.items() if name.startswith("derived/")],
    "excluded": excluded})
write_json("redactions.json", {"method": "Credential-bearing HTTP headers, URL credentials/query fields, token patterns and private-key markers were scanned; only exported copies may change.",
    "original_files_modified": False, "redacted_files": redactions,
    "note": "The two x-77-nzt CDN response fields are conservatively redacted; they are not asserted to be account credentials."})

input_rows = []
for row in inputs["source_downloads"]:
    source = dict(row)
    if "qemu" in row.get("url", ""):
        source["validation_basis"] = "official HTTPS URL, recorded SHA256 and xz integrity test; no independent upstream signature/checksum verification claimed"
    elif "nasm" in row.get("url", ""):
        source["validation_basis"] = "official HTTPS URL and index, recorded SHA256; expected_sha256 is null and no independent upstream checksum verification is claimed"
    else:
        source["validation_basis"] = "download SHA256 equals existing repository source lock or pinned build-script hash"
    input_rows.append(source)
for row in inputs["host_qt_official_packages"]:
    input_rows.append(dict(row, validation_basis="official Updates.xml package identity and official per-file SHA1 matched; local SHA256 also recorded"))

summary = {
    "schema": "xos-ssg-p2f-build-evidence-v1",
    "packaged_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "source_commit": commit, "source_tree": tree, "packaging_worktree_head": head,
    "build_status": "BUILT", "scope": "build evidence only; guest results are maintained by the parent report",
    "historical_guest_status_note": "Original current-environment.json and payloads-verified.json say NOT_RUN because they were written at the build-to-test handoff; these originals are preserved unchanged.",
    "parallelism": inputs["parallelism"], "inputs": input_rows,
    "tool_versions": environment["tool_versions"], "payload_tools": manifest["tools"],
    "qemu": environment["qemu"], "host_qt": environment["host_qt"],
    "sdk_manifest_sha256": environment["sdk_manifest_sha256"],
    "system": {"build_id": system["build_id"], "manifest_sha256": sha((ROOT / "build/ssg_p2f/system/manifest.json").read_bytes()),
        "legacy_images_available": system["legacy_images_available"],
        "xos_img_sha256": sha((ROOT / "build/ssg_p2f/system/xos.img").read_bytes())},
    "artifacts": artifact_check, "browser_receipts_rechecked": browser_checks,
    "qt_static_archives": runtime["qt_archives"], "session_receipt_note": session["record_type"],
    "failure_and_recovery_records": [".cache/ssg_p2f/logs/nasm-sha.log", ".cache/ssg_p2f/logs/host-qt-icu-layout.json",
        ".cache/ssg_p2f/logs/qemu-initial-failure.json", ".cache/ssg_p2f/logs/qemu-redownload.log",
        ".cache/ssg_p2f/downloads/qemu-download-verified.json", ".cache/ssg_p2f/logs/qemu-extraction-exclusions.json",
        ".cache/ssg_p2f/logs/qemu-install.log", ".cache/ssg_p2f/logs/qemu-firmware-audit.json",
        ".cache/ssg_p2f/logs/qemu-source-integrity-repair.json", ".cache/ssg_p2f/logs/qemu-install-retry.log",
        ".cache/ssg_p2f/logs/qemu-install-retry-receipt.json"],
    "archive": {"path": archive.name, "bytes": archive.stat().st_size,
                "sha256": sha(archive.read_bytes()), "members": len(records),
                "uncompressed_member_bytes": sum(map(len, records.values()))},
    "redaction_file_count": len(redactions),
    "limitations": ["Build success is not a guest/ABI qualification.", "Qt compilation emitted warnings; full log is retained.",
        "No dash adaptation or dash qualification is claimed.", "No large executable, image, source archive or firmware blob is included.",
        "Original transient extraction exception text was not separately saved; contemporaneous failure JSON and raw download/install logs are retained.",
        "The cause of the QEMU archive and UEFI-file truncations was not established."]
}
write_json("summary.json", summary)

lines = ["# Build command record", "", "Commands below are grouped by dependency stage, not a claim that every operation ran sequentially. GCC/Qt used at most 4 jobs, QEMU 2, with at most 6 combined. No guest was run by this packager.", "",
         "Paths are environment-variable templates rather than verbatim host paths. `derived/top-level-commands.json` is a readable index of those records. The two reconstructed/retained outer invocations are explicitly labelled; they are not a fabricated command transcript.", "",
         "```sh", "cd " + shell_template(portable(str(ROOT), PUBLIC_MAPPINGS, strict=True)), "source .cache/ssg_p2f/env.sh", "```", ""]
for row in command_rows:
    lines.extend(["## " + row["label"], "", "Evidence: `" + row["source"] + "`. Provenance: " + row["provenance"] +
                  (". Recorded return code: `" + str(row["returncode"]) + "`." if "returncode" in row else "."), "",
                  "```sh", "cd " + shell_template(row["cwd"]), " ".join(shell_template(arg) for arg in row["command"]), "```", ""])
lines.extend(["## Full internal commands", "", "The original system and SDK manifests and all component receipts contain the compile/link argument arrays. `build/ssg_p2f/sdk/compile.py` accompanies the Session command. Qt's `build.ninja`, `CMakeFiles/rules.ninja` and `CMakeCache.txt`, plus QEMU's `build.ninja` and configuration files, preserve generated command details. All configure/build/install stdout/stderr logs are included without truncation.", "",
              "## Preparation records", "", "Official source URLs, hashes, host Qt metadata and extraction logs are under `.cache/ssg_p2f/downloads/` and `.cache/ssg_p2f/logs/` in the archive. The three task-local orchestration scripts and `env.sh` are included. Host package installation logs are preserved; they are not a complete shell-session transcript. The host Qt ICU symlink layout and QEMU source-byte restoration are documented in their original JSON receipts.", ""])
(OUT / "COMMANDS.md").write_bytes(safe_public_bytes("\n".join(lines).encode(), "COMMANDS.md"))

readme = f"""# SSG-P2F build evidence — 2026-10-30

This package records a completed local build of the system, matching threading SDK, Qt Core/Gui/Widgets, Session, Consumer, Notes, ordinary Browser and test-only Oracle Browser. Source commit: `{commit}`; source tree: `{tree}`. It contains build evidence; guest qualification belongs to the parent report.

## Files

| File | Purpose |
| --- | --- |
| `summary.json` | Source identity, official input validation basis, tool binary hashes, system/SDK identities, ELF hashes and final receipt checks |
| `COMMANDS.md` | Full top-level configure/build/install command index with provenance and return codes |
| `build-records.tar.gz` | {len(records)} records: path-sanitized logs and manifest/receipt copies, selected build scripts/locks, generated Qt/QEMU command graphs |
| `inventory.json` | Every original/exported record's size and SHA-256; explicit exclusions; hashes of derived members |
| `redactions.json` | Exactly which exported copies changed and why |
| `SHA256SUMS` | Checksums of all other files in this directory |
| `package_build_evidence.py` | Packaging procedure; it only reads existing records and writes this directory |

The archive is **{archive.stat().st_size:,} bytes** ({archive.stat().st_size / 1048576:.3f} MiB). All archive paths are relative, all members are regular files, and no ELF, disk image, static library, downloaded source archive or firmware blob is included. The original local logs were not modified. Archive SHA-256: `{summary['archive']['sha256']}`.

## Evidence map

Archive paths preserve repository-relative locations:

- `.cache/ssg_p2f/logs/`: original bootstrap, runtime, tool, environment, payload and failure/recovery records; complete successful and failed build logs.
- `.cache/ssg_p2f/downloads/`: original download hash receipts and the official Qt `Updates.xml` metadata used for host package selection.
- `build/ssg_p2f/system/manifest.json` and `build/ssg_p2f/sdk/manifest.json`: system and threading SDK command/input/output manifests; the ordinary system SDK manifest is also included separately.
- `build/ssg_p2f/payloads/manifest.json`: original Session/Consumer/Notes/ordinary Browser build manifest. Session has no standalone original receipt; its actual command, source SHA and ELF SHA are in this manifest. `derived/session-summary.json` is explicitly a later extraction from this evidence, not a newly invented original receipt.
- `build/ssg_p2f/payloads/{{consumer,notes,browser}}/` and `build/ssg_p2f/oracle-browser/`: complete original component receipts, including Aurora library receipts. Ordinary Browser has `test_structure_oracle=false`; test Browser has `true`. Both sets of 43 inputs and all 3 compiler/archive tools were rehashed successfully during packaging.
- `.cache/ssg_p2f/threading_newlib/`, `build/threading_sdk_logs/`, Qt and QEMU build metadata: complete runtime build logs and exact configuration/command records.
- `derived/build-job-control.patch`: the two authorized `--jobs` additions, obtained from the base/current Git diff. Defaults stay at 8; this build used 4. No source/version/hash lock was relaxed.

## Input validation and limits

GCC, Binutils, newlib and Qt source SHA-256 values matched the existing repository locks or pinned build-script hashes. Official host Qt 6.8.3 packages were selected from Qt's `Updates.xml`, matched their official per-file SHA-1, and have separately recorded SHA-256 fingerprints. NASM and QEMU came from official HTTPS release URLs and have recorded SHA-256 fingerprints; this package does **not** claim an independently verified upstream SHA-256 or signature for either. QEMU's final archive passed `xz` integrity validation. The original NASM `verified: true` record means successful retrieval/local fingerprinting, not comparison with a missing expected checksum.

Original `current-environment.json` and `payloads-verified.json` contain `guest_validation: NOT_RUN`: those are historical snapshots from the build-to-test handoff; exported paths may be templated. They do not override the later guest evidence in the parent report. Compilation and hash checks alone do not qualify the ABI. Qt emitted compiler warnings; its full log is retained. No dash qualification is claimed.

## Failures and recovery

1. The attempted NASM `.sha256` URL returned HTTP 404. The failure log and official release directory listing are retained; no expected checksum was invented.
2. Host Qt `rcc` initially could not locate `libicui18n.so.73`. Original official ICU package files were linked into Qt's `lib` directory without changing binary bytes. Initial failure, final symlink layout, `moc`/`rcc` version output and tool hashes are retained.
3. The first QEMU archive was later found truncated (129,716,224 bytes). Its size/hash and extraction-failure summary are retained, along with the raw initial download and retry logs. The final official archive was 141,815,216 bytes and passed `xz` validation. A standalone raw extraction traceback was not separately saved. The truncation cause was not established.
4. Safe QEMU extraction omitted one unused absolute EDK2 host include symlink, explicitly recorded in `qemu-extraction-exclusions.json`.
5. The QEMU executable built successfully, but the first installation failed on a truncated extracted UEFI blob. All 78,695 regular source archive members were compared: only that blob differed; C/C++ source files matched. The blob was restored byte-for-byte from the verified archive. The original failed install log, exact before/after hashes, BIOS/VGA audit and successful install retry log/return code are retained. The damaged archive/blob themselves remain only in the original workspace and are excluded from this small package.

## Redaction and verification

Two QEMU CDN response tracking fields (`x-77-nzt` and `x-77-nzt-ray`) were conservatively replaced with `[REDACTED]` in the exported `qemu-head.log`; they are not asserted to be account credentials. No account authorization header, credential-bearing URL or token pattern was found. `inventory.json` records both the original and exported SHA-256; `redactions.json` records the exact transformations. Original local files remain byte-for-byte unchanged.

From this directory, `sha256sum -c SHA256SUMS` verifies the public package. `tar -tzf build-records.tar.gz` lists the copied records. The packaging procedure also reopened the archive and verified every member's bytes against its export inventory.
"""
(OUT / "README.md").write_text(readme)

with tarfile.open(archive, "r:gz") as tar:
    members = tar.getmembers()
    assert len(members) == len(records)
    for member in members:
        assert member.isfile() and not Path(member.name).is_absolute() and ".." not in Path(member.name).parts
        assert tar.extractfile(member).read() == records[member.name]

for name in selected:
    expected = next(row["original_sha256"] for row in inventory if row["path"] == name)
    assert sha((ROOT / name).read_bytes()) == expected, "Original changed while packaging: " + name
files = sorted(path for path in OUT.iterdir() if path.is_file() and path.name != "SHA256SUMS")
(OUT / "SHA256SUMS").write_text("".join(sha(path.read_bytes()) + "  " + path.name + "\n" for path in files))
total = sum(path.stat().st_size for path in OUT.iterdir() if path.is_file())
assert total <= 3 * 1024 * 1024, total
print(json.dumps({"files": {path.name: path.stat().st_size for path in sorted(OUT.iterdir()) if path.is_file()},
                  "total_bytes": total, "archive_sha256": summary["archive"]["sha256"],
                  "members": len(records), "redacted_files": len(redactions),
                  "archive_roundtrip_verified": True, "original_files_unchanged": True}, indent=2))
