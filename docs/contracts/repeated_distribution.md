# Accepted R1 distribution repetition

## Scope and entry gate

`scripts/repeat_glibc_distribution.py` repeats the already accepted R1 consumer
workflow. The pinned inputs are in
[`config/release/p1_j_r1_repeat.json`](../../config/release/p1_j_r1_repeat.json).
The script requires both the first R1 qualification and the recorded verified
public delivery, checks their exact bytes, and binds the accepted bundle to the
single asset selected by that delivery receipt. The automation does not create
first qualification, approve a different bundle, or upload a release.

The native system source is the recorded R1 commit. The runner source is a
separately recorded clean Git commit. These identities are deliberately distinct:
repeating the accepted distribution does not qualify a newer kernel, runtime,
network profile or application SDK.

The host SDK launcher and its tools, the accepted glibc application SDK, and the
frozen rollback SDK are each recorded. Their roles do not permit combining libc
headers, startup objects or sysroots across profiles. The historical rollback
SDK is retained for the existing release gate; receiver applications use their
bound glibc material.

## Commands and fresh output ownership

From a clean checkout containing the pinned historical source commit:

```sh
python3 scripts/repeat_glibc_distribution.py run \
  --bundle "${XOS_R1_BUNDLE}" \
  --frozen-sdk "${XOS_R1_FROZEN_SDK_ARCHIVE}" \
  --sdk-launcher "${XOS_SDK_LAUNCHER}" \
  --output "${XOS_FIRST_REPEAT}"

python3 scripts/repeat_glibc_distribution.py run \
  --bundle "${XOS_R1_BUNDLE}" \
  --frozen-sdk "${XOS_R1_FROZEN_SDK_ARCHIVE}" \
  --sdk-launcher "${XOS_SDK_LAUNCHER}" \
  --output "${XOS_SECOND_REPEAT}"

python3 scripts/repeat_glibc_distribution.py compare \
  --runs "${XOS_FIRST_REPEAT}" "${XOS_SECOND_REPEAT}" \
  --output "${XOS_REPEAT_COMPARISON}"
```

Both run directories and the comparison output must be absent. Run and compare
are host-side commands in a real source checkout with accessible Git metadata;
a worktree mounted alone into an SDK without its external Git common directory
is not sufficient for recording the verifier commit. A run records a
new UUID before starting, uses its own source archives, extracted receiver kits,
SDK bindings, rebuilt system, guest media, reports and frozen output. The script
has no resume operation. A failed run remains failed even if an investigator
later completes individual diagnostic stages manually.

The SDK launcher receives `XOS_QMP_TRANSPORT=pipe` explicitly because its clean
environment does not inherit an outer shell's QMP setting. This is the existing
FIFO transport of the guest harness, without a new networking or guest ABI.

## Required sequence

1. Verify the first qualification, public-delivery receipt, bundle and rollback
   SDK bytes. Require a clean tracked runner and archive both source revisions.
2. Reject unsafe archive members, duplicates, links and excessive extraction
   sizes. Verify the outer inventory and the frozen distribution checksums.
3. Rebuild the exact recorded native system. Check every recorded source input,
   build identity and host tool. Compare ISO, flat kernel and ordinary hello ELF
   bytes with R1. Check the debug ELF's loadable binary, layout and symbol table
   separately, retaining the original and rebuilt debug identities.
4. Run all five receiver kits in separately mounted directories without a
   checkout mounted into them. Relink xypm, dash, the thirteen daily programs,
   GNU Make and CPython, checking original and replacement artifact identities.
5. Verify component-source correspondence and glibc archive/signature/key/SDK
   bindings. This stage does not recompile all upstream components.
6. Run the package installation/lifecycle guest and native GNU compiler guest,
   including cold-boot execution. Reopen the distributed archives in a fresh
   receiver and verify GNU Seed files in the actual package lifecycle disk.
7. Run all five real guest substitution suites using the receiver outputs.
8. Exercise wrong hash, stale SDK and missing source rejection while frozen
   output is still absent. Recheck every required positive result, then freeze.
9. Recheck original bundle, rollback SDK and launcher bytes before the outer run
   can become `passed`.

Each subprocess has a separate retained log. An unsuccessful subprocess or
binding check makes the outer run fail; successful earlier stages do not make
that attempt eligible for comparison.

## Temporary media and evidence lifecycle

Guest disks can be large. Their lifecycle follows the final real consumer:

| Temporary medium | Last consumer before removal |
| --- | --- |
| GNU build disk | Completed combined package/GNU guest workflow |
| Package lifecycle disk | Archive receiver preflight and GNU Seed readback |
| Installer snapshot | Completed xypm substitution guest, after all five substitution reports pass |

Removal requires a completed successful producer and consumer report, the exact
expected full-disk SHA-256, and a unique retirement receipt. The receipt records
the disk identity and the immutable producer/consumer report identities before
unlinking. The final freeze requires exactly these three completed retirements,
checks that all three paths are absent, and rechecks the report bytes. No active
guest media is removed.

After qualification, a delivery operator may retain frozen files, original
reports, source archives and actual produced artifacts while reclaiming
reproducible expansions. Such retention needs a complete original inventory,
byte verification of every retained file, a final original-input recheck and an
explicit removal receipt. Original report paths and statuses must remain
unchanged; relocation is recorded separately. A hash of a removed intermediate
is a receipt, not the intermediate itself. After separate runs have completed,
identical immutable files may share same-filesystem storage if their separately
produced bytes, sizes and modes are fully verified and that physical reuse is
recorded. It does not authorize skipping a run stage or rewriting its metadata.

## Comparison and publication limits

The completed run envelope has its own bounded UTF-8 JSON reader: at most
1 MiB and sixteen levels, with duplicate keys, invalid Unicode, floats and
non-finite values rejected. The XPK package metadata parser keeps its existing
eight-level limit. The actual completed make-output envelope reaches nine
levels, including the outer run record.

Comparison requires distinct UUIDs and distinct directories, two passed fresh
runs, unchanged qualification records and unchanged recorded frozen assets.
It requires the same bundle, runner/lock/launcher, source archives, native source,
first-qualification gate and rollback SDK, then compares SDK bindings, native
system identities and all receiver identities. The output separately records
the read-only verifier commit/script digest, ordered raw run identities and the
canonical digest of each complete frozen inventory. It checks the two real
source archive files, exact frozen names, every file's size/digest and equality
of all fifteen immutable distribution assets. Guest timing and per-run disk
changes remain separately recorded instead of being treated as deterministic
bytes.

The delivery also checks the exact frozen directory inventory and each retained
artifact's complete size and SHA-256. Public reports derived from local records
must identify path redaction and raw origin identities. Their flat
`manifest.json` is the only digest index for public sibling leaves; raw origin
digests are not relabeled as digests of exported files.

The qualified boundary is the named accepted R1 consumer workflow. It does not
establish full glibc/GCC/upstream source recompilation, hardware testing,
arbitrary physical power-loss recovery, a new installed dynamic network profile,
or publication of a new release. The first R1 upgrade-fault and frozen-SDK
round-trip campaigns remain prerequisites with their original evidence; they
are not claimed as fresh J guest runs. Additional configurations require their
own source/profile binding and target evidence.
