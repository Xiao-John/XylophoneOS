# P1-D authenticated distribution acceptance

`qualification.json` is the final result. The raw test run passed five fresh
guest boots and the raw official run passed three. Together they exercised
15 actual target installers and eight GNU libc application executions. The
implementation, SDK artifacts, protected publication and application startup
were executed; build receipts retaining `built_not_run` describe the earlier
build step and are qualified by these separate run reports.

## Evidence map

| Files | Purpose |
| --- | --- |
| `test_guest_report.json`, `official_guest_report.json` | Actual per-case diagnostics, authority revisions, input hashes and system/SDK binding |
| `test_*_serial_base64.json`, `official_*_serial_base64.json` | Lossless raw serial for all eight successful boots |
| `host_authentication*.json` | 30 ordinary and 30 ASan/UBSan real-EVP cases with exact replay vectors |
| `p3_regression.log`, `package_cache_regression.log` | Existing bounded-resolver and image-cache regression results |
| `release_replay_vectors.json`, `official_signing_receipts.json` | Exact signed bytes, signatures, index/lock/generation bytes and independently configured public identities |
| `system_build_report.json`, `system_manifest.json` | C/B/E source snapshot, precise D overlay, explicit 300-second profile and final system build identity |
| `shared_runtime_manifest.json`, `runtime_final_source_binding.json` | One shared GNU runtime, nine artifacts and all 471 native/recipe/port input comparisons |
| `application_*`, `distribution_*`, `glibc_sdk_*`, `target_openssl_report.json` | Program generation, immutable path transformation, exact SDK profile and real target libcrypto |
| `official_installer_*`, `installer_*public_path_gate.json` | Public installer build/pack identity and explicit debug stripping proof |
| `first_cas_failure_*`, `logging_close_failure_*`, `dead_channel_diagnostic_*`, `lease_console_diagnostic_*` | Preserved failed runs, including the unobserved direct expiry trace |
| `*cleanup.json` | Authorized reproducible-source/object cleanup and lossless failed-disk compression with before/after identity checks |
| `recovery_checkpoint.json` | Historical WIP state; deliberately not relabeled as a pass |

The eight negative cases in test scenario 33 cover absent actual publisher
delegation, changed signed bytes, expiry, wrong signing key, dependency cycle,
dependency conflict, missing XPK and changed XPK payload. Scenario 34 interrupts
staging after a newly created object is synced. The old protected catalog and
application remain usable. Scenario 35 upgrades and scenario 36 rejects the old
signed release. Every boot completes actual GNU READY/ACK and checks exact
stdout and successful exit for the selected generation.

## Integrity and presentation

Run from the repository root:

```sh
python3 scripts/verify_evidence_index.py docs/reports/p1d_authenticated_distribution/manifest.json
python3 tests/check_public_evidence_paths.py --index --base origin/main
```

Each JSON public projection identifies its untouched raw input digest and
size. Only SDK/workspace location prefixes and JSON presentation are projected;
actual results, source/artifact digests, commands and bounds remain. The
`${XOS_TOOLCHAIN_HOME}` and `${XOS_SDK_WORKSPACE}` strings are explicit
configuration templates. A projected file has its own digest in `manifest.json`;
it must not be mistaken for the original build receipt bytes.

Serial wrappers contain `encoding`, `bytes`, `sha256` and `data`. Decode `data`
as base64 and verify the decoded size/hash. The evidence manifest separately
binds the wrapper file. Release replay vectors also retain exact base64 bytes;
signature verification uses the domain `XOS-XYPM-RELEASE-V1` plus one zero byte
and the original metadata bytes, without parsing and reserializing them.

## Reproduction inputs

Use the independently supplied SDK with manifest
`0c876bac53354501159df75813711002c41baede650f1878116bb64a80a8190b`,
tree `ce808de26f1ede38a543c94bba5d5a5592606c71305267854cb57ea519429254`
and profile `xos-x86_64-glibc-p1-20261128-v1`. The profile bytes have digest
`736d3353d9aad14d019dbc678b77dbb8f6fe8585bed84b71e1f858566a7a3f9f`.
The matching OpenSSL receipt and archive are recorded separately. The shared
runtime is built from the frozen C foundation source including the 96-byte
distribution bootstrap header; D does not rebuild or replace the capsule-v3
runtime during the guest suite.

The public installer recipe is:

```sh
python3 scripts/build_xypm.py \
  --sdk "${XOS_STATIC_SDK}" --profile "${XOS_PROFILE}" \
  --openssl-build "${XOS_OPENSSL_BUILD}" \
  --provisioning-source "${XOS_SOURCE}" \
  --repository-trust config/package/official_repository_trust_v1.json \
  --public-artifact
```

`scripts/build_xypm_distribution_guest.py --source-tree "${XOS_SOURCE}" --output
"${XOS_GUEST_BUILD}"` creates the isolated acceptance system with the production
C/B/E implementation and precisely recorded D fixture changes. The explicit
launch profile is 300 seconds, the default remains 30 seconds, each RPC is
bounded by five seconds and installer staging has one 120-second deadline.
The guest runner is `tests/xypm_distribution_guest.py`; all exact input hashes
are in the two run reports. Its `--official` mode accepts independently signed
metadata and rejects test private keys/fault-installer options.

The two historical official releases were valid from 2026-11-28 11:54:31 to
2026-11-29 11:55:31 UTC. A later real-time run must reject these expired bytes.
In Asia/Shanghai (UTC+08:00), this is 2026-11-28 19:54:31 to 2026-11-29
19:55:31. Only these signed repository metadata bytes expire; the SDK itself
does not expire with them.
Future publication must use a new increasing sequence and newly authorized
release; never re-sign different metadata under an already published sequence
or roll the platform clock back to revive these samples. Host cryptographic
replay uses the recorded logical times and exact historical bytes.

## Two distinct stripping proofs

The dedicated native supervisor omits nonloaded symbols and proves exact entry
and complete PT_LOAD byte equality before its image is included in the system
manifest. The public GNU installer uses explicit `--strip-debug` before packing.
Its first PT_LOAD includes the ELF header, so `e_shoff`, `e_shnum` and
`e_shstrndx` change. The installer proof preserves entry, the entire program
header table, mapping properties and every other mapped byte, and records both
raw segment hashes. It does **not** claim that all raw PT_LOAD hashes match.
The original ELF and failed first stricter guard are retained separately.

## Scope

The trusted parent and daemon use kernel-observed peers and real accepted
sessions to delegate the catalog publisher. PPR12 success from that daemon is
required before staging. A signature, child-supplied PID or parent ACK cannot
grant the role. The path writes exclusively created immutable objects and
publishes one protected checkpoint/catalog CAS; P2 maintenance is unchanged.

These boots use an explicit developer COM1 authority backend. P1-C separately
records the independent UID provider acceptance. D qualifies interrupted
staging; C/E separately qualify ambiguous durable CAS results. Default 30-second
backing expiry is a source-and-timing inference supported by the successful
explicit-profile run, not an observed console expiry trace. No arbitrary
physical power-loss, default deployment, new network transport, automatic
execution/network authorization or shared GNU fork claim is added.
