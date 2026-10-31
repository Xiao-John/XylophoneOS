# SSG-P2F build evidence — 2026-10-30

This package records a completed local build of the system, matching threading SDK, Qt Core/Gui/Widgets, Session, Consumer, Notes, ordinary Browser and test-only Oracle Browser. Source commit: `0a63648d53e4a7491320111f053f8b93882fbdab`; source tree: `058657a521988be8f2d5ec8535e70359d5290ed7`. It contains build evidence; guest qualification belongs to the parent report.

## Files

| File | Purpose |
| --- | --- |
| `summary.json` | Source identity, official input validation basis, tool binary hashes, system/SDK identities, ELF hashes and final receipt checks |
| `COMMANDS.md` | Full top-level configure/build/install command index with provenance and return codes |
| `build-records.tar.gz` | 151 records: path-sanitized logs and manifest/receipt copies, selected build scripts/locks, generated Qt/QEMU command graphs |
| `inventory.json` | Every original/exported record's size and SHA-256; explicit exclusions; hashes of derived members |
| `redactions.json` | Exactly which exported copies changed and why |
| `SHA256SUMS` | Checksums of all other files in this directory |
| `package_build_evidence.py` | Packaging procedure; it only reads existing records and writes this directory |

The exported archive contains 151 records with normalized owner metadata and path-sanitized member content. The local originals were not modified. Exported archive SHA-256: e1abea1cf12d67338ce3c86475963c33cfbd3543f47e43ecfa2f0137209d0af1. The inventory records original and exported member hashes.

The following descriptions refer to historical build records. Exported copies may contain path templates, and their hashes are recorded in the inventory.

## Evidence map

Archive paths preserve repository-relative locations:

- `.cache/ssg_p2f/logs/`: original bootstrap, runtime, tool, environment, payload and failure/recovery records; complete successful and failed build logs.
- `.cache/ssg_p2f/downloads/`: original download hash receipts and the official Qt `Updates.xml` metadata used for host package selection.
- `build/ssg_p2f/system/manifest.json` and `build/ssg_p2f/sdk/manifest.json`: system and threading SDK command/input/output manifests; the ordinary system SDK manifest is also included separately.
- `build/ssg_p2f/payloads/manifest.json`: original Session/Consumer/Notes/ordinary Browser build manifest. Session has no standalone original receipt; its actual command, source SHA and ELF SHA are in this manifest. `derived/session-summary.json` is explicitly a later extraction from this evidence, not a newly invented original receipt.
- `build/ssg_p2f/payloads/{consumer,notes,browser}/` and `build/ssg_p2f/oracle-browser/`: complete original component receipts, including Aurora library receipts. Ordinary Browser has `test_structure_oracle=false`; test Browser has `true`. Both sets of 43 inputs and all 3 compiler/archive tools were rehashed successfully during packaging.
- `.cache/ssg_p2f/threading_newlib/`, `build/threading_sdk_logs/`, Qt and QEMU build metadata: complete runtime build logs and exact configuration/command records.
- `derived/build-job-control.patch`: the two authorized `--jobs` additions, obtained from the base/current Git diff. Defaults stay at 8; this build used 4. No source/version/hash lock was relaxed.

## Input validation and limits

GCC, Binutils, newlib and Qt source SHA-256 values matched the existing repository locks or pinned build-script hashes. Official host Qt 6.8.3 packages were selected from Qt's `Updates.xml`, matched their official per-file SHA-1, and have separately recorded SHA-256 fingerprints. NASM and QEMU came from official HTTPS release URLs and have recorded SHA-256 fingerprints; this package does **not** claim an independently verified upstream SHA-256 or signature for either. QEMU's final archive passed `xz` integrity validation. The original NASM `verified: true` record means successful retrieval/local fingerprinting, not comparison with a missing expected checksum.

Original `current-environment.json` and `payloads-verified.json` contain `guest_validation: NOT_RUN`: those are historical snapshots from the build-to-test handoff; paths in exported copies may be templated. They do not override the later guest evidence in the parent report. Compilation and hash checks alone do not qualify the ABI. Qt emitted compiler warnings; its full log is retained. No dash qualification is claimed.

## Failures and recovery

1. The attempted NASM `.sha256` URL returned HTTP 404. The failure log and official release directory listing are retained; no expected checksum was invented.
2. Host Qt `rcc` initially could not locate `libicui18n.so.73`. Original official ICU package files were linked into Qt's `lib` directory without changing binary bytes. Initial failure, final symlink layout, `moc`/`rcc` version output and tool hashes are retained.
3. The first QEMU archive was later found truncated (129,716,224 bytes). Its size/hash and extraction-failure summary are retained, along with the raw initial download and retry logs. The final official archive was 141,815,216 bytes and passed `xz` validation. A standalone raw extraction traceback was not separately saved. The truncation cause was not established.
4. Safe QEMU extraction omitted one unused absolute EDK2 host include symlink, explicitly recorded in `qemu-extraction-exclusions.json`.
5. The QEMU executable built successfully, but the first installation failed on a truncated extracted UEFI blob. All 78,695 regular source archive members were compared: only that blob differed; C/C++ source files matched. The blob was restored byte-for-byte from the verified archive. The original failed install log, exact before/after hashes, BIOS/VGA audit and successful install retry log/return code are retained. The damaged archive/blob themselves remain only in the original workspace and are excluded from this small package.

## Redaction and verification

Path templates and normalized archive ownership were added in a later Issue 37 export. Two QEMU CDN response tracking fields (`x-77-nzt` and `x-77-nzt-ray`) were conservatively replaced with `[REDACTED]` in the exported `qemu-head.log`; they are not asserted to be account credentials. No account authorization header, credential-bearing URL or token pattern was found. `inventory.json` records both the original and exported SHA-256; `redactions.json` records the exact transformations. Original local files remain byte-for-byte unchanged.

From this directory, `sha256sum -c SHA256SUMS` verifies the public package. `tar -tzf build-records.tar.gz` lists the copied records. The packaging procedure also reopened the archive and verified every member's bytes against its export inventory.
