# XylophoneOS P4A-R1 — release compatibility recheck

2026-11-05. This is a compatibility and regression recheck of PR #76; it does
not develop a new SSG feature or alter a published asset.

## Baseline

| Item | Observed revision |
|---|---|
| `v0.0.2-1103` peeled tag | `071330f3b196d357c4a823f1719793b449513b86` |
| Release system build | `8356e45af316fc93`, built from `6fe330ce` |
| PR #76 base | `59ac60db7f68fa0f9b13b56025df8549f1a72c5e` |
| PR #76 head | `a7c7db01f2b61e7828876841b34c30087d4d09d9` |

The tag source, system-image source, and PR head are distinct commits.

## Result matrix

| Required result | Status | Evidence |
|---|---|---|
| `RELEASE_ASSET_INTEGRITY` | `PARTIAL` | All five current Release attachments match the GitHub API size and SHA-256. The live Release has no `sources` attachment; `CHECKSUMS.sha256` and the frozen receipt disagree. See `asset_audit.json` and `MAINTAINER_NOTE.md`. |
| `RELEASE_SDK_DIRECT_BUILD` | `FAIL` | The official SDK contains lowercase `xos::file::client` and matching `libxos.a` symbols, so the old file-client overlay is unnecessary for that API. The direct P4A build still fails on the missing thread-profile headers/runtime and standard-library profile; the P4A link recipe also omits the separately packaged loader archive. |
| `RELEASE_QT_COMPATIBILITY` | `FAIL` | The Qt asset’s generated headers point at the packager’s build/source paths, and generated configuration headers are not present there in the package. Direct compile/link attempts fail. The isolated compatibility build used the official Qt static libraries with relocated header paths and generated configuration sidecars. |
| `RELEASE_IMAGE_GUEST_SUBSCRIPTION` | `PASS` | The official `xos.iso` booted in QEMU. Four independent processes delivered Browser and Notes initial states over the event Pipe; both exact ACKs were independently re-decoded and verified. Pipe capacity returned to 8/8. |
| `RELEASE_GUEST_FAULT_CASES` | `PASS` | All 15 scenario runs and both fresh-baseline resynchronization runs passed independent verification, including Notes edits, Browser scrolling, revocation/protection, provider exits, wrong/duplicate ACK, malformed frames, and Pipe backpressure. |
| `P4A_PREMATURE_EOF` | `PASS` | Closing the event Pipe before either initial source state produced zero events/ACKs, Subscriber exit code 5, an unclean Supervisor child result, and Supervisor exit code 1. The independent verifier passed. |
| `P4A_P3C_REGRESSION` | `PASS` | The P3C contract guest and ordinary Console Watch regression passed on the official release images. |
| `PR76_REVIEW_READINESS` | `PARTIAL` | The direct SDK/Qt asset combination is not build-compatible as published, and the repeated guest stress batch passed 11/12. The release metadata discrepancy also awaits maintainer reconciliation. |

The full repeat run completed 11/12 short stress sessions. Run 06 retained the
historical Browser shutdown/cancel behavior (`P3B_SOURCE_EXIT ... cancelled=1`);
the root cause remains `EXIT_RACE_ROOT_CAUSE=UNRESOLVED`. No failure run was
removed. The other 15 scenario results, two resync checks, 25 Subscriber-state
checks, P3C contract checks, and ordinary Console Watch check are in
`validation_summary.json`.

After that matrix, a final-source rebuild produced all nine targets again. Its
Supervisor, Subscriber, Notes, and test-fixture ELFs match the matrix build;
the Browser ELF hashes differ because the build output path changed. The final
rebuild's first-subscription and premature-EOF QEMU runs, each with independent
frame/lifecycle verification, also passed.

## Compatibility boundary

The exact direct build was attempted first and failed. For functional QEMU
coverage, the isolated compatibility view kept the official lowercase file
client API and original official Qt static libraries, while supplying the
thread profile and generated Qt headers that the published SDK/Qt package
does not contain in usable form. This is not an official SDK direct-build
PASS, and no release tarball or image was edited.

The event ACK remains an in-memory Subscriber state acknowledgement only.
There is no replay after a lost/incorrect ACK; a new session needs new source
instances and baselines. `globalAtomicSnapshot=NOT_IMPLEMENTED` remains, and
the native-thread exit-race root cause is still unresolved.
