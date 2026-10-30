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

To reproduce, use the prepared paths in the P1 report, build with
`scripts/build_ssg_p1.py` to a fresh output directory, then run:

```sh
QEMU=../runtime/qemu-prefix/opt/qemu/bin/qemu-system-x86_64 \
python3 tests/ssg_text_range_guest.py \
  --image ../XylophoneOS-aurora-glass/build/aurora_glass/system-v5/xos.img \
  --session build/ssg-p2b-notes-final/session.elf \
  --consumer build/ssg-p2b-notes-final/consumer/ssg-consumer.elf \
  --notes build/ssg-p2b-notes-final/notes/notes.elf \
  --output build/ssg-p2b-notes-new-guest
```
