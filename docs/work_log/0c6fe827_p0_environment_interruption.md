# P0 environment interruption and continuation checkpoint

## Scope and interruption

Checkpoint: 2026-11-28, Asia/Singapore (the corresponding report directories
are dated 2026-11-27 UTC). User authorization covers implementing every planned
P0, developing with the verified pre-release SDK, opening a PR per module and
updating the next-round P1 table. It does not authorize merging main or
publishing a release.

The execution environment became unavailable during ongoing qualification.
Subsequent read-only access returned "No usable execution environment is
available". The orchestration runtime was also replaced, discarding its
in-memory publication state. GitHub remained accessible. We re-read its open
PRs, main ref and campaign branch before this documentation update.

Remote state at this checkpoint:

- Main: `daf2bd24ce92525ce61054ebe585ab0e88ed06e4`.
- Open campaign PRs: #397 through #411; plan plus fourteen implementation or
  validation PRs. Their scopes and dependency bases are in
  [the campaign table](../plans/p0_completion.md).
- Launch-control's attempted tree upload did not yield a durable verified
  remote result. A subsequent lookup of the exact expected tree returned 404.
- Remote lookups of the local launch-control and DHCP commit identities also
  returned 404. Neither is described as a submitted PR.
- No campaign code was merged and no release was published.

This document preserves last observed identities, not a copy of uncommitted
source or a promise that the unavailable workspace is recoverable. After the
workspace returns, inspect the actual bytes, git state and raw evidence first.
Do not overwrite or clean them based on this summary.

## Verified development inputs

The development environment is the normal launcher from the official Linux
x86-64 Preview 2 SDK. Archive SHA-256:

`60df6913fe2a56517e645c93673ebd9590ba3dd90acc56030c80c3738955cac9`

Observed tools include GCC 16.2.0, Binutils 2.47.20260726, NASM 3.02 and
QEMU 11.1.3. The bundled target sysroot is newlib; glibc SDK/runtime trees were
built separately from authenticated inputs. The launcher did not provide an
offline network-namespace qualification.

A workspace-only LLVM 19 supplement was prepared for full kernel/debugger
smoke. Its Debian package metadata was checked through a verified InRelease
signature and SHA-256 package records. It did not replace the pre-release SDK.
Preserve that audit and include its exact identities when the final smoke
result is collected.

## Complete local modules awaiting publication

| Module / worktree name | Last local identity | Last successful qualification |
| --- | --- | --- |
| launch control / xylophoneos-launch-control | commit `c4fd6ff0470f4bf62b977f212517ef0eed2e76fb`; tree `0ae46b3e08966543dc2e564ac9b1e8c213e1f89e` | host 14, ASan/UBSan 14, target C/C++, native guest 11 scenarios x 3 rounds = 33; evidence index 23/23; public-path check 41/41 |
| actual DHCP service / xylophoneos-network-dhcp | commit `e6ef17a4d5a32451fbdf0edcd53c74aa47b02aaf`; tree `dfd38ee7fd1252f8116d6e60a2b50d957e20f5ca` | real guest 7/7; actual lwIP/DHCP/ACD ASan/UBSan 17; static regression 32 + 2; profile 32; SDK malformed snapshot 16 plus closed receive 2; evidence 25/25; public-path check 54/54 |

Launch control's system build was `2864ec94d58b8ee0`, ISO SHA-256
`bdb48e9d142aab9cf25e5ab6a29e0219692e8a8ab9342067cdec0cfdeea32c30`.
It includes real same-PID exec, READY/ACK, precommit cancel, postcommit failure,
revocation checks, timeout, actual stale queued reply recovery and wait-any.
Its contract/work log are:

- `docs/contracts/launch_control.md`
- `docs/work_log/62ae4d19_launch_control_and_wait_pump.md`
- `docs/reports/p0_launch_control_20261127/manifest.json`

DHCP's final system was `c1b74fffb3822956`. Seven real scenarios cover renew,
expire, NAK/configuration change, rebind, malformed replies, ACD conflict and
conflict/backoff/recovery. The last scenario exposed a real stale-issuer
constraint in SELECTING; the production fix and negative/positive regression
were included in the final commit. Software ARP queues and ordinary sessions
are retired at the configuration barrier; frames already accepted by a NIC
cannot be recalled.

- `docs/contracts/network_dhcp_profile.md`
- `docs/work_log/8f6bd320_dhcp_real_lease_service.md`
- `docs/reports/net_dhcp_service_20261127/manifest.json`

The DHCP local branch contains egress, the already published helper, the
independent peer fixture and final integration. Do not duplicate the helper in
the integration tree. The peer is part of the operational DHCP module.

## Public runtime: tested core, incomplete overall D3/D4

Worktree: xylophoneos-runtime. Its last committed HEAD was abbreviated
`01f71a9`; subsequent public-loader changes were still uncommitted when the
environment failed. They must be recovered and preserved before cleanup.

Final C runtime:

| Artifact | Identity |
| --- | --- |
| runtime build directory | sdk_builds/runtime_public_p0_v6 |
| runtime manifest SHA-256 | `d5c12ee3f4b2a8d3365516c1239b33561568c0f8431122adfe1fb2378c48a392` |
| frozen system/source | build/p0_public_source_v4/build/system; build/p0_public_source_v4 |
| system build ID | `ade21018a872dccf` |
| system ISO SHA-256 | `b162d062ba3890a9d3b88a4cdffda9c6401670cd0d45ca526074b4f6aab2ca6d` |
| native SDK manifest SHA-256 | `cc2d29f58eeff6e504e1433a2bc164c7b2779c536273fb3f07e88e0079c992d3` |
| C generation approved root | `f7559c549b35f62190519991fbcd32047b97cbc6cd20bc8554cb63f81136065a` |

The final source included standard SONAME '+' support. That fix was necessary
for libstdc++.so.6; earlier successful C results were not relabelled after the
source change. The final C report, `build/p0_public_guest_v6/report.json`,
passed seven real scenarios:

1. GNU libc/rtld, constructors, TLS, environment, auxv and Files.
2. Genuine same-PID execve, shared FD offset, CLOEXEC and successor READY.
3. Precommit missing-target failure preserving the old PID and FD state.
4. Postcommit constructor exit 47 observed as the actual child result.
5. Namespace replacement after capture still using the original OFD.
6. LD_PRELOAD rejection.
7. Mismatched expected receipt rejection.

Final activation additionally passed three rounds and fifteen actual GNU
launches, with resource baseline [129697, 3, 1] after each round. A complete
same-pin closure is checked before changing active catalog state. A candidate
missing libc fails without changing sequence/active root; an approved old root
can be revalidated and restored; revoked roots cannot activate or spawn.
Write-capable open of the formerly pinned objects while the controller remains
alive demonstrates pin release.

- `docs/work_log/b3af190d_dynamic_launch_activation_lifecycle.md`
- `docs/reports/dynamic_launch_lifecycle_20261127/manifest.json`: 32/32.
- `build/p0_activation_guest_v6_strict`: final real guest.
- Production launch.cpp SHA-256:
  `da40716996f2e99ee34f2e69a354b166281fc3fc2d532b0b51778d6008d252c0`.
- Production dynamic_launch.hpp SHA-256:
  `69dacae63b42b513526acb833bb6582ab933bc06710fd61cd10db643704deef3`.
- Host orchestration and ASan/UBSan each passed 12 groups. The explicitly
  modeled transport-failure cases do not constitute real guest fault injection.

Public C++ libraries and program were built from the same final public GNU
inputs, with native notes and an eight-object staged generation:

- sdk_builds/public_gcc_v6
- sdk_builds/public_cxx_sample_v6/program.so
- sdk_builds/public_cxx_app_v6/program.pie
- sdk_builds/public_cxx_stage_v6

The C++ guest call did not return a result before the environment failure.
Do not count it as run or passed. Required real markers are
D2_STD_THREAD_OK, D2_STD_THREAD_APP_TLS_DTOR and D2_SHARED_CXX_TLS_DTOR.

The installable native controller is implemented in
`src/user/programs/dynamic_launcher.cpp` and
`scripts/build_dynamic_launcher.py`. Its first version passed six real
guest cases, recorded in `build/p0_dynamic_launcher_guest_v1/report.json`.
Before publication, add required independently approved
`--sdk-tree-sha256` checking before and after snapshot copy: the existing
manifest/provenance chain authenticates the native archives, but does not
independently approve all headers/crt0/user.ld. Rebuild and retest the modified
launcher; do not carry v1's result over.

Other unclosed P0 items:

- Real xsh and dash entry paths (the successful C tests used the supervisor's
  exec-driver and a native controller). The in-progress dash build's final
  status was not collected.
- Actual dlopen/dlmopen/dlclose behavior for the permitted startup-only
  profile, with explicit enforcement if needed.
- Final current-source ELF/admission host and target records.
- Public-runtime contract/work log, sanitized evidence, local commits and PR.
- Full final integrated SDK/system qualification.

The explicit approved-root native controller is a suitable public entry
shape. It does not justify claiming arbitrary runtime DSO loading, persistent
global authority or a glibc-default dynamic SDK.

## Reusable static C++ builder

Worktree xylophoneos-static-cxx contains the uncommitted new
`scripts/build_glibc_static_cxx.py`. It builds libstdc++, libsupc++ and the
five required synchronized unwind members from authenticated GCC sources,
without requiring a previous composed C++ SDK. It checks the C SDK and tools,
retains all other libgcc members and packages its exact recipe/imports/locks.

Final build: sdk_builds/static_cxx_p0_v2.

- SDK manifest SHA-256:
  `6f1b2a4fbfb90696972e269fdc4cad57e5d8b043e6c9df7b35f05426fa5b1771`.
- SDK tree SHA-256:
  `505f8cb3b7a39dc8345edb5bd76095403d23782c5e229fd1cb89f4aa1883c92d`.
- Profile SHA-256:
  `b5546946def0acc07fc976d8a92dd6bc4868189ae594438a1e9dbada9c6a5f06`.
- Detached consumer: static_cxx_receiver_final. It built/check/packed C and C++
  consumers with only the exported kit and consumer mounted.
- Real report: `build/p0_static_cxx_guest_final/report.json`, status passed,
  11 runs, system `152d9a46ed1e9471`, baseline [129806, 2, 0].
- ISO SHA-256:
  `19fa007b1fed90ac63354d720f5532324cb14aadf0d2781c3b8934d803db53b5`.

Those runs exercised global constructors, threads/TLS/destructors, unwind,
stack bounds, C path operations, stock xypm and dash on one FAT disk with
readback identity checks. This SDK used the earlier C base and is not the final
combined P0 SDK. Recipe-receiver inspection, public evidence/work log, commit
and PR were not finished. The final R1 SDK must be rebuilt from final source.

## Combined qualification and actual R1 still pending

The combined integration branch last committed `574a8dd` and contained the
already published modules, DHCP helper/peer and the QMP transport change. Its
last validated intermediate system `c71bcfeec46ce657` passed real IPC
lifecycle/authority/quota (12 invocations) and absolute-deadline (three rounds,
18 scenario groups) checks. Combined Files checks passed 63 FD cases and 15
actual Files/FatFs cases; the native Files deadline bridge passed 13 host cases.

Full smoke initially rejected the SDK QEMU version; another attempt correctly
rejected a stale test-source binding. The local fix updates the pin from 11.1.2
to 11.1.3 and accepts only its exact upstream version plus package suffix. The
subsequent rebuild/smoke output was not collected. Preserve failed logs and
rebuild source-bound images after any test/script change.

R1 input preparation is not an executed release:

- Frozen newlib 0.0.1-1024 SDK/image archives and their release manifest were
  downloaded and hash verified. The SDK's profile inspection passed. Actual
  cold-boot rollback with shared work data is still pending.
- GNU Seed 0.0.2-1103 donor manifest/images/sources were downloaded and matched
  their repository-pinned hashes.
- Complete locked sbase checkout was obtained at
  `c546c3a5724c81cee9a11d816a38ccdf17472129`, tree
  `a58d176568a1b33d435a7628740b68289ea5c07a`.
- CPython 3.14.9, IDNA 3.20 and GNU Make 4.4.1 inputs were hash checked.
- The zlib builder requires 1.3.2.tar.xz, SHA-256
  `d7a0654783a4da529d1bb793b7ad9c3318020af77667bcae35f95d0e42a792f3`.
  The previously fetched 1.3.1 archive is not that input and must not be used.

After final source is committed, create one final static C/C++ kit with
directories, threads and stdio_transfer, then use it consistently:

1. Build zlib, CPython with zlib, IDNA XPK and GNU Make; retain every first-link
   log and object needed by collectors. CPython's current release packager
   accepts the declared zlib extension set, not an unqualified OpenSSL variant.
2. Run glibc_release_pipeline.py build with actual ordinary and installer guest
   gates. It rebuilds the root build directory; do not run concurrently with
   another root build.
3. Package the candidate, packages, GNU Seed donor and Make; collect matching
   component source using the actual full source commit and exact receipts.
4. Collect xypm, dash, daily, Make and CPython relink materials. Run receiver
   relinks and actual guest checks; staging manifests alone is insufficient.
5. Stage complete v6 supplements, run release smoke, exact-build gates and
   atomic freeze with a state binding this kit and the genuine frozen newlib
   rollback SDK.
6. Execute glibc -> frozen newlib -> glibc cold-boot rollback and verify work
   data, then publish module/combination PRs. Do not publish release assets.

Preserve first dash make.log before an incremental build replaces its link
command. xypm's ordinary builder removes temporary backend objects: reconstruct
the exact five translation-unit build from the same project/receipt and require
byte-identical stock ELF before relink collection. CPython's relink frozen
report/log must come from this same build, not a previous release.

## Documentation validation at this checkpoint

This update was authored through the repository API after workspace loss.
The normal repository scripts could not be rerun. The prior module evidence
and public-path gate results above remain their original results. For these
two new Markdown edits, the API payload was checked for private workspace
paths, trailing whitespace, unresolved placeholders and accidental edits
outside the plan/work log, then fetched back for byte comparison. This narrow
documentation check is not reported as the repository-wide test suite.

The next implementation action requires recovery of the actual workspace.
Remaining P0 requirements stay P0. The updated P1 table describes the next
round and does not declare this campaign complete.
