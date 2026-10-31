# Issue 37 — Browser evidence export

This branch contains path-sanitized copies of the PR10 evidence. Archive members and exported hashes are listed in browser-redactions.json; original and exported container hashes differ. IPC request/response frames and synthetic HTML inputs were checked byte-for-byte against the earlier archives. The full history and inherited base are not remediated by this ordinary commit.

The audited export contains 32 rebuilt archives. Of their regular members,
8,609 were byte-identical and 118 had path or related metadata changes; owner
metadata was normalized. Eight checksum manifests were rechecked. Six existing
Browser verifiers were replayed against the appropriate sanitized captures.
The P2F structural and wire checks were replayed separately, without claiming
that all historical external build inputs were reverified. See
`browser-validation.json` for the bounded results and fresh QEMU controls.
Fresh guest runs also covered the P2G4 A/B comparison, P2G5 interruption and
recovery, and P2G6 exhaustion, reload and cross-document navigation. Their
independent verifiers passed and resource counters returned to baseline.

Guest report generators now serialize configurable path templates and fail on
unknown private paths. They still execute the actual configured paths. The P2F
build-evidence packager templates records and checks them before writing an
export. Provide the applicable `XOS_ROOT`, `XOS_IMAGE`, `XOS_QEMU`,
`XOS_SESSION_ELF`, `XOS_CONSUMER_ELF`, `XOS_BROWSER_ELF`, `XOS_INPUT`, and
`XOS_TEST_OUT` values. Build receipts can also require `XOS_SDK_PREFIX`,
`XOS_BUILD_DIR`, `XOS_QT_SOURCE`, `XOS_HOST_QT`, `XOS_BINUTILS`, or the
additional roots recorded in the templates. These values name equivalent
artifacts on the machine running the test; they are not historical host paths.

For example, in a clean checkout with a matching test-Oracle Browser and its
receipt, the following invokes the guest and validates the recorded structure:

```sh
export XOS_ROOT="$(git rev-parse --show-toplevel)"
export QEMU="$XOS_QEMU"
python3 "$XOS_ROOT/tests/ssg_browser_pages_probe.py" \
  --image "$XOS_IMAGE" --session "$XOS_SESSION_ELF" \
  --consumer "$XOS_CONSUMER_ELF" --browser "$XOS_BROWSER_ELF" \
  --browser-receipt "$XOS_BROWSER_RECEIPT" --input "$XOS_INPUT" \
  --require-oracle --output "$XOS_TEST_OUT"
```

The output directory must be new. The harness creates its temporary work disk
and QMP socket. Before publishing, scan the actual index and pass the local
identity to `tests/check_public_evidence_paths.py --index --base "$XOS_PR_BASE"
--deny-identity "$XOS_PRIVATE_IDENTITY"`. The P2F independent audit still
requires its recorded source and binary inputs to be available and hash-match;
set the XOS path variables before running it. It does not silently skip missing
inputs. Raw host logs remain local and are not attached by these instructions.
