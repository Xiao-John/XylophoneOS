# Native generation activation and exact reclamation

**The rebuilt native/GNU composition passed all 21 checks across three rounds,
with 12 actual public GNU C launches.** Every round restored the exact baseline
of **129779 free pages, 2 tasks, 0 completions**. The seven cases execute in a
single native controller in each round; catalog state is not replaced between
activation, rollback and revocation.

## Qualified composition

The final run uses native system build `e8b8ba5e2645c5c2`, frozen source
`86a06b0a`, and the freshly rebuilt public GNU runtime v3 / C stage v3. The C
producer source is `ba3e9d275f4b17f1fdf0ac2bbb4d79d5deae1605`, materialized from
Git objects and checked against the exact staged source hashes. The runner
checks every system artifact, the immutable system source, native SDK, C SDK,
source file, approved generation and installed ELF before and after execution.
The ELF and root identities are recorded in the receipts; this run does not
reuse or relabel the preceding GNU v2 qualification.

The final three-root launcher is
`38a742644418dc0139eaefd736a68359904856c295ffb95c0483aa3ed18bdee4`;
the final native fixture is
`9e7a0d5f60c6b84b86c68a026315963f454f0b18893308336f79428944add380`.
The program sources are a separate complete archive of the frozen native
revision with exactly five owned files overlaid from their original Git blobs.
`source_overlay.json` records each source identity. The existing builder's
strict whole-SDK header comparison remains intact; unrelated newer network
headers were obtained from the matching full source, not ignored.

## Seven actual cases per round

1. Install generation 0, then start and successfully reap the ordinary public
   C application with its real GNU constructor, TLS, relocations and environment.
2. Retain a generation-0 file pin, activate generation 1, read the same old
   handle/inode, close it exactly once, then successfully launch generation 1.
3. Reject an activation with a stale sequence without changing active state.
4. Preflight a third approved manifest whose main is deliberately absent;
   preserve generation 1 and its sequence, then successfully launch it again.
5. Explicitly roll back to approved generation 0 and successfully launch it.
6. Reject stale revocation, revoke generation 1 with the current sequence,
   deny future admission/activation of that root, and retain allowed root 0.
7. Revoke active root 0; reject new capture with the existing no-active state
   and reject admission. The final sequence is 5 and revocation bitmap is 3.

The probe uses ordinary public inspect/spawn and `sdk::wait_flags`. It sends
`DYNAMIC_ENV=verified` to the real C application. It does not model Files, IPC,
kernel completion, GNU startup, or resource reclamation.

## Earlier attempts retained separately

The preceding frozen `fb881e4e` / GNU v2 composition also passed three complete
rounds, 21 checks and 12 real C launches, with exact baseline 129781/2/0. Those
records remain under `baseline_*` and retain their own system/ELF/root hashes.

The first runner invocation failed before starting QEMU because the SDK's
workdir mapping could not resolve an external worktree gitdir. An explicit
read-only source-repository option fixed that portability problem. The first
executed probe then passed its four C launches and first six cases, but its
last assertion incorrectly expected `revoked` where the existing catalog and
host contract return `state` after clearing active. The fixture expectation
was corrected in `c864db2b`; production code and native SDK bytes were unchanged.
Both failures remain explicitly failed in their own reports and serial log.

The additional `native_cross_binding.json` is a post-run check that the C
program builder's complete native SDK snapshot equals the frozen system SDK.
It also distinguishes the two existing inventory algorithms: `sdk_receipt`
hashes files plus directory inventory; `xos_app` hashes the file inventory.
Their digest strings differ by design, while both describe the same checked
SDK bytes. This supplementary check does not change any guest result.

## Reproduction and evidence boundaries

Use `tests/dynamic_generation_guest.py` with the frozen system/source, the
three-root launcher and fixture builds, the actual program/runtime stages,
explicit program producer revision, the shared read-only Git object source,
both independent C SDK anchors, a new output directory and `--repeat 3`.
The CLI input receipts record all identities. The source materialization is
not replaced with whichever producer script happens to be in the latest tree.

`manifest.json` is the only exported per-directory hash root; git authenticates
it. `conversion.json` records original unpublished input hashes and the precise
mechanical conversion: known environment paths are templates, JSON keys are
sorted, and serial line endings/trailing whitespace are normalized. All
observations and source/ELF/root/SDK identity values are preserved. Raw receipt
hashes still identify the unpublished original inputs, never exported siblings.

`${XOS_ROOT}` denotes the owned checkout, `${XOS_R2_ROOT}` the frozen complete
source plus owned overlays, `${XOS_NATIVE_SOURCE}` the original frozen system
source, `${XOS_BASELINE_NATIVE_SOURCE}` its earlier baseline,
`${XOS_WORK_DISK_DIR}` the SDK work mount, and `${XOS_GUEST_WORK_DIR}` the disposable
test disk directory. The Preview 2 prefix/dependency templates identify tools.
Resolve these explicitly for a replay.

This is the volatile per-controller P0 activation/rollback gate. Durable policy,
cross-descendant revocation and process-tree budgets remain P1. Later GNU
producer corrections require explicit byte-identity mapping or new execution;
this report's v3 hashes and observations must not be changed to stand for them.
