# Issue 37 — path and archive hygiene

This directory records a bounded audit, not a claim that public Git history has
been erased. A normal fix commit does not remove earlier Git objects, remote
copies, or upstream material. History rewriting and force-pushing were not
performed. `history-commit-scan.json` describes the commits in the two fork PR
ranges; it does not cover all inherited commits or all possible path encodings.
The inspected Notes range had findings in 2 of 2 commits, and the inspected
Browser range had findings in 8 of 11 commits. These are findings in those
commit deltas, not a count of independent disclosures.

The earlier 1,714 findings are classified in `historical-classification.json`
without matched path text. The classification identifies 1,704 findings also
present in the common base and ten portability findings in the Notes delta.
Two apparent Linux home paths were checked and found to be Home/End key names;
three other home-pattern findings remain for review. A finding identifies a
file or archive member and is not necessarily one distinct disclosed path.
`INHERITED_FROM_BASE` identifies origin, not remediation.

Ten Notes records were redacted and then their command arrays were converted
to explicitly labelled templates. `notes-redactions.json` records original and
exported hashes. Both P1 archives were rebuilt: their member lists are retained,
one report member in each has changed content, and all other regular-member
bytes were checked against the original. Archive owner metadata was normalized;
the containers and metadata are not byte-identical to the originals.

`tests/check_public_evidence_paths.py` scans tracked working-tree files by
default, actual stage-zero Git blobs with `--index`, or a commit with
`--commit`. `--base REF` limits the selection to the candidate delta. It checks
compressed members, names, link targets, tar owner/PAX metadata, UTF-8 and
binary text fragments, and optional explicit identities. Unreadable or
over-limit evidence is `UNVERIFIED` and prevents a pass. System paths are not
automatically classified as personal homes. The scanner is a bounded check,
not proof that no possible encoding or private datum exists.

Before a public commit, scan the actual index after staging all intended files:

```sh
python3 tests/check_public_evidence_paths.py --index --base "$XOS_PR_BASE" \
  --deny-identity "$XOS_PRIVATE_IDENTITY" --output "$XOS_TEST_OUT/index-scan.json"
python3 -m unittest discover -s tests -p 'test_public_evidence_paths.py' -v
```

Set `XOS_PRIVATE_IDENTITY` locally; its value and matched bytes are not written
to the scan report. Do not publish raw local logs or old scan indexes that have
not been reviewed. See the separate Notes live-range report for actual guest
results and reproduction instructions. Browser remediation is tracked
independently on its own PR branch.
