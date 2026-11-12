# 59ae1469 UTF-8 M2 filename boundary probe

## Scope and result

Started the next concrete multilingual roadmap slice on `codex/multilingual-m2`, based
on `origin/main` at `a676e21`. Existing UTF-8 path support already had Chinese
create/list/read/rename/sync/reboot evidence. This change extends its private-disk
guest probe for three documented M2 gaps without changing file ABI or asserting
Unicode normalization/case folding:

- Non-BMP filename `🧪-𠮷.txt`: create, enumerate, rename, read and unlink through
  the rebuilt libc path.
- Exact full path length 255 UTF-8 bytes succeeds, while 256 bytes is rejected;
  the 255-byte name is also found in directory output.
- Twenty 231-byte UTF-8 filenames with a shared long prefix are created with
  distinct contents, enumerated without duplicate/missing entries across file
  service response pages, then reopened and removed by their full names. The
  common prefix stresses FatFs generated short-name alias allocation while
  clients use LFN spellings; manually obtaining/using a short alias and
  comparing its object identity remain outside this probe.

The multilingual plan now records existing M3 width/combining-codepoint evidence
from work logs 0174 and 0182 and describes its grapheme/locale limits accurately.

## Files changed

- `tests/fixtures/utf8_names/libc_probe.cpp`: non-BMP, byte-boundary, long-name
  and paginated directory cases, each with a guest output marker.
- `tests/utf8_filename_smoke.py`: requires all markers and syncs the private test
  disk after the new cases.
- `docs/plans/multilingual.md`: reconcile M3 evidence and current M2 status.
- `docs/work_log/README.md` and this record.

## Checks

- Host strict syntax check for the guest C++ fixture — PASS. This does not run
  FatFs, the file service, or the guest libc.
- Python `py_compile`, `tests/docs_consistency.py`,
  `tests/abi_doc_consistency.py`, and `git diff --check` — PASS.
- Target build, `tests/utf8_filename_smoke.py`, and QEMU guest execution — NOT RUN.
  No runtime M2 qualification is claimed.

Run after building a matching image and SDK, on the harness's isolated work disk:

```text
python3 tests/utf8_filename_smoke.py \
  --image build/utf8_m2_boundary/xos.img \
  --sdk build/utf8_m2_boundary/sdk \
  --report build/utf8_m2_boundary/utf8_filename_report.json
```

## Remaining boundary

The route still requires disk-crafted invalid/overlong LFN handling, directory
entry I/O faults and full-disk behavior, an explicit alias-spelling identity test,
and a frozen Unicode case/normalization policy before any broader claim. Guest
results must bind source, SDK, image and private disk; host syntax is not product
evidence.
