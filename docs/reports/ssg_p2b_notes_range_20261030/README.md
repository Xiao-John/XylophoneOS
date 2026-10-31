# SSG-P2B Notes text range — partial, unqualified

This is a narrow work-in-progress, not completion of SSG-P2B. Browser continuation,
consistent multipage scene baselines, complete-baseline Diff, cancellation and
GUI responsiveness during Browser pagination are NOT IMPLEMENTED. The original
large Browser regression remains FAILED as documented in the unchanged P2 report.

The private prewired Notes provider accepts `text_range` only for a previously
observed QPlainTextEdit identity and current source instance and epoch. Each call
rechecks text permission, ancestry and application-supplied protection. It returns
an application-local document-change generation; a nonzero offset requires that
same generation and an edit returns `RESET_REQUIRED`. Replaced/destroyed widgets
and replaced documents are refused. Text is indexed in UTF-16 code units, and
start/end cannot split surrogate pairs. A range is at most 1024 units and reports
selection and scroll metadata, which can change independently of document text.
It is document text, not a claim about visible glyphs. It does not publish a
SceneStream snapshot or grant observation authority. This generation and the
prewired instance are not authentication mechanisms.

`tests/ssg_text_range_guest.py` ran the real XOS Notes provider and separate
consumer through existing pipes using synthetic text. Eight ranges reconstructed
all 3,623 UTF-16 units exactly, including emoji and line breaks, from a single
instance, epoch and generation. The serial log and all response payloads are
retained here. The display-service resource tuple before and after the session
was `[130235, 3, 1]`. The report records input hashes and QEMU command. The
scratch FAT disk and QMP socket named in that command are temporary.

This run does **not** test edit/revision invalidation, permission withdrawal,
protected nodes, malformed offsets, empty documents, individual surrogate
boundary cases, provider death, large Browser scenes or input during pagination.
Do not treat the new code as security or full P2B qualification. The P1 guest regression was rerun with these new artifacts and reports 17
scoped checks passed; the report and raw evidence are retained here. Its small
Browser fixture does not qualify large-page pagination. Full static Qt
distribution and relinking license review is NOT_RUN; do not infer it from prior
registered-material checks. Test frames and logs contain synthetic text.

The report and archived regression evidence were redacted for Issue #37; see
`docs/reports/issue37_path_hygiene/notes-redactions.json` for original and
redacted hashes. The rebuilt archive is not the original byte sequence.

To reproduce with independently prepared artifacts, set `XOS_IMAGE`,
`XOS_SESSION_ELF`, `XOS_CONSUMER_ELF`, `XOS_NOTES_ELF`, `XOS_TEST_OUT`, and
`QEMU`, then run:

```sh
export XOS_ROOT="$(git rev-parse --show-toplevel)"
python3 tests/ssg_text_range_guest.py \
  --image "${XOS_IMAGE}" --session "${XOS_SESSION_ELF}" \
  --consumer "${XOS_CONSUMER_ELF}" --notes "${XOS_NOTES_ELF}" \
  --output "${XOS_TEST_OUT}"
```
The current harness requires the output directory to be inside `XOS_ROOT/build`.
