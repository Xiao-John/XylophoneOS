# Approved native dynamic launcher: build qualification

This directory records the production `dynamic-run` builder and separate native
generation probe. Initial and corrected target builds passed in the Preview 2
SDK: the real C generation launcher, the three-generation launcher, and the
native activation probe. These receipts intentionally retain `built_not_run` / `guest: not_run`.
The public-runtime integration runner supplies native execution evidence
separately against the exact resulting bytes.

The production source is checkpoint `285d5ec2`; the generation probe and its
builder are checkpoint `a686ccb6`. The native system build is
`36d8733989de37f6`, checked against its own frozen source snapshot, complete
exported SDK, archive-member provenance and compiler identity. The independent
C SDK manifest and complete-tree anchors are recorded in each successful
receipt. Complete native and C SDK snapshots are checked before and after
copying and linking. These are distinct SDKs with distinct roles.

Checkpoint `3a8887aa` then corrects ordinary process creation authority
inheritance. The initial guest main could run, but public `posix_spawn` exposed
the missing `copy_from_caller` prepare hook. Corrected builds have separate
receipts and new ELF hashes; the earlier build records remain unchanged. No
earlier guest result is relabeled with a new executable identity.

## Actual checks

- One-root launcher: 123264 bytes, real public GNU C generation.
- Three-root launcher: 123312 bytes, valid C generation 0, its second explicitly
  approved generation, and a structurally valid third generation whose main is
  deliberately absent from the guest filesystem.
- R2 native probe: 123200 bytes, the same three compiled roots. It exercises
  one controller's 0→1→0 transition with four real public C launches, a retained
  old pin, failed candidate preservation, stale updates, and revocation. This
  directory records its build only.
- Incorrect manifest anchor: rejected before compilation; no ELF created.
- Incorrect complete-tree anchor: rejected before compilation; no ELF created.

After the authority correction, the one-root launcher is 123328 bytes, the
three-root launcher is 123376 bytes, and the generation probe is 123264 bytes.
Those three `*_authority_build.json` receipts are the inputs for subsequent
guest qualification.

The two negative invocations change just one caller-supplied anchor to 64 zeroes.
`negative_anchor_checks.json` records the assertions against the actual failed
receipts and absence of output ELF; both actual error logs are retained. The
correct anchors are never learned from adjacent guest metadata.

Both production and probe use strict freestanding GCC/G++ 16.2.0 target builds
with warnings treated as errors. Each final executable stays below the ordinary
native loader's 128 KiB input-file bound. Actual artifacts, source files, tools,
approved roots, build commands and complete input inventories remain in the
receipts. A successful build is not a statement that GNU startup or the native
activation tests ran.

## Evidence and reproduction

`manifest.json` is the flat hash root for all other files in this directory.
The git tree authenticates that root. `conversion.json` records each original,
unpublished input hash, source checkpoint, exported filename and conversion rule.
Only known environment paths were replaced. No source, ELF, root, compiler or
SDK identity was relabeled. In the probe receipt, `launcher_receipt_sha256`
continues to identify the original unpublished launcher receipt, not the
path-normalized exported sibling. Exported sibling hashes occur only in the
root manifest.

`${XOS_ROOT}` is the exact checkout, `${XOS_WORK_DISK_DIR}` the Preview 2 work
mount, `${XOS_PREVIEW2_PREFIX}` the tool prefix and `${XOS_PREVIEW2_CELLAR}` its
packaged dependency directory. Resolve these templates explicitly before
replaying commands. Actual CLI inputs and the independent approval boundary are
documented in the work log `b18c320a_approved_dynamic_launcher.md` and the dynamic
closure contract. Each invocation requires a new output directory.

This qualification does not claim terminal-actor forwarding, durable policy,
cross-descendant revocation, arbitrary runtime `dlopen`, or process-tree budgets.
