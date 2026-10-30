# SSG P2F: independent Browser structure qualification

P2F continues fork PR #10's existing pagination. It does not implement a second
Provider, a production Broker, paged Diff, or interaction recovery. Its acceptance
target is **A1: the independent Consumer receives the complete structure and text
of one fixed, actually loaded liteHTML document**. A1 alone does not qualify all
rendering geometry or the original aggregate Gate A.

The current upstream architecture rules govern this experiment. This work does
not approve a constitutional amendment, merge an unapproved dependency, or change
the kernel, public system ABI, QPA, drivers, PR #20, or installed LocalPilot.

## Independent guest reference

The ordinary Browser build has no Oracle. The explicit
`src/ports/aurora_browser/build.py --test-structure-oracle` build defines
`XOS_SSG_TEST_ORACLE` and records that decision in the ELF build receipt.
The test reference is absent without that macro. There is no Oracle IPC operation
or added production permission. It requires the existing explicit text permission.

`test_structure_oracle.hpp` recursively visits the actual `doc->root()` and every
child in the engine's native order. It does not use `scene_page`, `scene_snapshot`,
`scene_ids`, `PageFrame`, cursors, page limits, or the Provider's end condition.
It retains head, hidden, and off-viewport subtrees, including the engine's actual
text/whitespace node splitting. It does not infer nodes from HTML tag counts.

The reference is bounded to 4096 nodes, depth 32, and 256 KiB of UTF-8 text/href
values. A reference limit/allocation failure cannot produce an accepted Oracle.
These are test bounds, not expansions of the Browser's HTML admission or paging
budgets. In particular, production text nodes still have the existing 1024 UTF-16
code-unit limit; resource refusal is not complete reading.

The GUI thread captures the reference immediately before the first paging call
and again after traversal exhaustion, before the terminal response is sent.
Both references bind the loaded input SHA-256, document path, Provider process,
session instance, source epoch and revision. Exact equality establishes the fixed
document used in this test; it does not qualify concurrent mutation recovery.

Each reference node contains a memory-address-independent path (`0/1/3`), parent
path, preorder ordinal, child index/count, tag, role, complete text for text nodes,
and complete href for links. Empty values are distinct from absent fields.

## Canonical structure digest

`canonicalFormat` is `netstring-utf8-v1`. Start with the ASCII bytes
`XOS-LITEHTML-STRUCTURE-V1\n`. For each preorder node, append eleven netstrings in
this order:

1. `path`
2. `parentPath` (empty for root)
3. decimal `ordinal`
4. decimal `childIndex`
5. decimal `childCount`
6. `tag`
7. `role`
8. `1` when text is present, otherwise `0`
9. text, or empty when absent
10. `1` when href is present, otherwise `0`
11. href, or empty when absent

A netstring is the decimal UTF-8 byte length, a colon, those exact bytes, and a
comma. Append one LF after each node. `structureSha256` is SHA-256 of these bytes.
This avoids assumptions about Qt/Python JSON escaping or object-key ordering.

## Consumer and verifier responsibilities

The production Consumer checks framing, source continuity, page fields, unique
IDs, one root, parents preceding children, and legal preorder progression. It
still emits `completeness=ORACLE_REQUIRED`: local consistency cannot discover a
whole omitted subtree. It does not publish a verified paged baseline or Diff.

`tests/ssg_browser_structure.py` decodes exact Consumer request/response payloads
and the separate Oracle records. It rejects incomplete, duplicate, orphaned or
out-of-order chunks, wrong lengths, duplicate JSON keys, invalid values, filtered
queries, source changes, invalid continuation, and premature/missing termination.

It reconstructs normalized paths from Consumer parent IDs and sibling order,
without requiring the reference and Provider to share IDs. It checks the complete
node set, root, every parent, child count, sibling order, role, tag, exact text,
UTF-16 text range, and href against the independent reference. It also requires
distinct parent/Provider/Consumer PIDs and successful child exit records. The
outer probe requires exact return to the display-service resource counters.

The host `.wire` files contain the exact logged payload plus the fixed 12-byte
SSG1 header reconstructed from validated protocol fields. Their provenance is
explicit: they are not a second packet capture. The serial log and individual
JSON payloads preserve the original observation. No host-generated model is used
as the expected guest tree.

## Fixtures and reproduction

`tests/fixtures/ssg_browser/p2d.html` is unchanged: 424 bytes, SHA-256
`37fff0e9d875d3196f3d547a4f65e0a329b1466623eac9d2a502554d18c41e0f`.
The old 32-node observation is not an expected answer supplied to the Oracle.

`p2f.html` adds nested and sibling elements, headings, variable-length text,
spaces/newlines, preserved preformatted text, Unicode entities, multiple links,
hidden descendants, and off-viewport content within the existing admission rules.
Its first link has a distinct local target so a real hit can identify that link.
`p2f_text_limit.html` contains one hidden 1025-unit text token; the required outcome
is an explicit resource refusal, never A1 success.

First build a matching current XOS image, Session, Consumer, ordinary Browser and
test Browser using the existing SDK/Qt build scripts. Give the two Browser builds
separate output directories. Example parameterized commands:

```sh
python3 src/ports/aurora_browser/build.py \
  --sdk "$SSG_SDK" --qt-build "$SSG_QT_BUILD" --qt-source "$SSG_QT_SOURCE" \
  --host-qt "$SSG_HOST_QT" --binutils "$SSG_BINUTILS" \
  --output "$SSG_TEST_BROWSER" --test-structure-oracle

python3 tests/ssg_browser_pages_probe.py \
  --image "$SSG_IMAGE" --image-format iso --session "$SSG_SESSION" \
  --browser "$SSG_TEST_BROWSER" --consumer "$SSG_CONSUMER" \
  --input tests/fixtures/ssg_browser/p2d.html --output "$SSG_NEW_OUTPUT_A" \
  --require-oracle --link-hit

python3 tests/ssg_browser_pages_probe.py \
  --image "$SSG_IMAGE" --image-format iso --session "$SSG_SESSION" \
  --browser "$SSG_TEST_BROWSER" --consumer "$SSG_CONSUMER" \
  --input tests/fixtures/ssg_browser/p2f.html --output "$SSG_NEW_OUTPUT_B" \
  --require-oracle

python3 tests/ssg_browser_pages_probe.py \
  --image "$SSG_IMAGE" --image-format iso --session "$SSG_SESSION" \
  --browser "$SSG_TEST_BROWSER" --consumer "$SSG_CONSUMER" \
  --input tests/fixtures/ssg_browser/p2f_text_limit.html --output "$SSG_NEW_OUTPUT_LIMIT" \
  --expect-resource-limit
```

Use `--image-format floppy` for an actual floppy image. Each output directory must
be new. A test receipt adjacent to the Browser ELF is required, or supply
`--browser-receipt` explicitly. ELF and relevant current source hashes must match
the receipt; an unrelated executable cannot qualify from old logs.

Run `python3 tests/ssg_browser_structure_test.py` to exercise the verifier's
explicitly synthetic/mutated negative cases. These tests prove that the verifier
rejects corrupted captures; they are not successful guest observations.

## Geometry and remaining gates

`--link-hit` runs only **after** paging finishes. It selects a complete, visible
link fragment from the actual Consumer data, checks its viewport clipping, records
a screenshot, sends real QEMU PS/2 movement/button events, and requires navigation
to that link's unique prepared target. This is a scoped one-link geometry check.
It is not interaction during paging, and it does not qualify Gate C.

DOM structure, text, rendered fragments, viewport visibility, and global screen
occlusion remain separately reported. `fragmentsComplete=false` never becomes
complete geometry through A1. Oracle instrumentation adds work and serial output,
so its timings are not a production performance result. The ordinary Browser must
run the affected P1/small Browser regressions separately. The legacy larger-page
nonpaged Diff assertion stays unchanged and keeps its actual pass/fail result.

Gate B (complete A/B baselines and Consumer Diff), Gate C (input during pagination
and recovery), Notes safety, multi-provider aggregation, and LocalPilot integration
remain outside this change. Results belong in a fresh dated report directory.
