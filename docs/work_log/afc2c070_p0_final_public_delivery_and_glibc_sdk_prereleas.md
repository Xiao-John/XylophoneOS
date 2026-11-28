# afc2c070 P0 final public delivery and glibc SDK prerelease

## Scope and current delivery gate

This final integration record joins the per-module public PRs and fresh minimal
evidence with the actual SDK and R1 distribution assets. Both are published and
verified through independent public downloads. The [delivery receipt](../releases/p0_glibc_preview_3_delivery.json)
records the seven uploaded asset identities and the completed public-delivery gate.
The original [P0 acceptance requirements](../plans/p0_completion.md) are retained.

The SDK was built at `8b2dee22a3272692603e9d01534c9b648375d04f`; its system is
`4a379155cac2fbbf`. R1 retains producer `3964200d524fd39f3a95c166800832623c5f3591`,
system `7c8c59058be0b5f1` and its own profile. The later recovery workflow at
`b60b9aea68f6f270abc0e97077f92adeaa2e72f8` validates the original SDK bytes;
it does not relabel them as a build of the newer main branch.

## Module delivery and qualification

Fresh network evidence was merged through #424–#427, the packaged static SDK
pipe regression through #428, generations through #429, public GNU startup
through #430, native integration through #432, and the complete R1 evidence
through #435. The zlib input URL and license lock digest fixes are #422/#423.
The host SDK recipe, verified host setup and draft recovery are #431/#433/#436.
The [campaign table](../plans/p0_completion.md) links every delivered module and
records counts and remaining contract boundaries. Parallel P1-A #434 and its
read-only observation/proposal qualification remain unchanged.

R1 includes five detached receivers for all 17 shipped static glibc programs,
byte-identical original relinks, actual one-member-libc replacements in the
guest, native C/C++/Make/Python composition, interrupted package recovery and
the four-cold-boot frozen-newlib roundtrip. The reports and 26 raw/export
provenance mappings remain frozen in #435. License material review records
zero active open, one deferred and seven not-applicable entries; it is not a
claim of universal legal clearance.

## SDK publication attempts

- [46109935710](https://github.com/Xiao-John/XylophoneOS/actions/runs/46109935710)
  failed the Ubuntu 24.04 Bubblewrap UID-map preflight before a build or release.
- [46110344041](https://github.com/Xiao-John/XylophoneOS/actions/runs/46110344041)
  passed the Ubuntu 22.04 / Python 3.12 host preflight, build and independent
  final-archive C/C++ consumer. All five assets uploaded, but the draft-by-tag
  lookup returned HTTP 404. The run remains a publication failure.
- [46113698404](https://github.com/Xiao-John/XylophoneOS/actions/runs/46113698404)
  correctly stopped at the existing-tag guard. Build and publication were skipped.
- [46114477779](https://github.com/Xiao-John/XylophoneOS/actions/runs/46114477779)
  was dispatched with the original tag and `recover_existing: true`. The
  authenticated five-asset download, token-free fresh C/C++ guest consumer,
  remote recheck and publication all passed. The original five asset IDs and
  bytes and the source tag remain unchanged. Publication completed at
  2026-11-28 14:00:04 Asia/Shanghai.

The recovery source/proof separation and 14 boundary tests are recorded in
[#436](https://github.com/Xiao-John/XylophoneOS/pull/436) and its
[work log](91ce8032_glibc_sdk_draft_release_lookup.md). The token-free consumer
step uses a fresh extraction and empty consumer directory. Original uploaded
assets and qualification bytes must remain unchanged, and the remote asset set
and actual tag ref must be checked around publication.

## Preserved distribution and workspace recovery

The full R1 outer tar is 430,346,240 bytes with SHA-256
`492c7b311431132398b84f62ff9357f516983039094559d41d4159e3e7e19ff4`.
It contains 20 frozen files plus README, bundle manifest and bundle checksums.
The restored outer archive matches its saved digest and all 22 listed inner
payload digests. The original frozen components were not rebuilt or changed.

An inactive temporary-workspace reset removed local build trees and some raw
temporary logs. GitHub commits, uploaded SDK draft assets, public evidence and
the durably saved R1 tar/checksum survived. The final documentation was restored;
the SDK recovery code was reconstructed and rechecked before #436. Retained
structured source/log digests are not claimed to restore lost raw log bytes.

## Final public delivery verification

All five SDK assets were downloaded from their public release URLs without
authentication and independently matched against server sizes/digests and
the four checksum entries. The fresh consumer ran the packaged C and C++ ELF
bytes with exit 0, preserved user data and returned resources to `129693/3/1`.
See the [public delivery evidence](../reports/p0_public_delivery_20261128/README.md).

The published SDK was also independently extracted to run the documented R1
C++ init/build/check/pack sequence. All commands passed, and the 13-payload XPK
was verified against the R1 profile and rejected by the host default profile.
Its embedded receipt and ELF match the new build. This specific generated
application was not run in a guest; the original R1 guest qualification is
unchanged. The report records actual tools and all relevant bindings.

R1 tar asset `803481989` and checksum asset `803482667` were uploaded to the
same prerelease. Independent unauthenticated downloads match the saved bytes.
The tar contains 23 regular files and one directory, with no links: all 22
bundle checksum entries, 19 frozen checksum entries and 20 frozen manifest
file sizes/digests pass. The original five SDK asset IDs/sizes/digests and the
`8b2dee22` tag remain unchanged; stable Latest remains `v0.0.2-1103`.

The final staged 14-file public-path scan is PUBLIC_READY with zero findings;
all seven new evidence leaves match the flat index. Relative links, JSON
references and the work log identifier pass. The qualification commands include:

```sh
# Run from the directory containing each matching downloaded asset set.
sha256sum -c SHA256SUMS
sha256sum -c p0-r1-glibc-release-20261128.tar.sha256
# Run from the candidate checkout after staging the actual final diff.
python3 tests/check_public_evidence_paths.py --index --base origin/main
python3 scripts/verify_evidence_index.py docs/reports/p0_public_delivery_20261128/manifest.json
```

The independent R1 public receiver additionally reads the tar without extraction,
rejects unexpected members/links and checks its inner checksum sets and manifest.
Its actual invocation and helper digest are retained in the download receipt.
This documentation milestone adds no new OS-build or guest qualification; the
module reports, SDK recovery consumer and R1 example retain their actual scopes.

Stable `v0.0.2-1103`, the separately qualified Qt profiles and original frozen
newlib rollback media keep their own identities. Installed DHCP with dynamic
GNU applications, connected-socket poll(0), concurrent close/revoke in poll,
pthread cancellation, physical NIC/power loss, trusted production time/entropy,
online dynamic loading, full WebCore and multiple-window composition are not
newly qualified by publication of these artifacts.
