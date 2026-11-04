# P3B checkpoint: preliminary combination

This is a historical checkpoint, not the final acceptance report. The branch is
stacked on the unmerged Browser PR #10 at `687b6b1fa2fa1600162843ab4b259511e817701f`.
The preliminary build used source commit `ede7ef3e6b846c6b893778049670bf7b46a84465`;
subsequent source changes require their own build and rerun. The raw local runs
are not included in this checkpoint. Do not infer completion of the stress suite,
all regressions, or the previous exit-race root cause from it.

A synthetic real-guest baseline from that build had three distinct processes,
34 Browser pages/267 nodes, and a 4,114-unit Notes document. The independent
liteHTML model and owner digest matched. The two sources were sampled in order,
not atomically; Notes was hidden because the display provides one exclusive
Surface. Browser and Notes both exited normally and measured resource counters
returned to their active-display baseline. Separate preliminary runs observed
real Notes editing, Browser scrolling/reload, permission refusal, process exits,
timeout, and truncated-frame handling. Each remains scoped to its own run.

| Preliminary artifact | SHA-256 |
| --- | --- |
| Build manifest | `d49773fc5aac2af5875425ef9abe56d952a9356fc2e9a49d0807de275514521d` |
| Test supervisor ELF | `e30392cfc33de68753eb2f183448314ae53b613deccbb108dfd528cf638688f3` |
| Test Browser ELF | `5b83a5c8ac02c6c433afd12d342a484169421f88d695f69f2a8cad88fba44398` |
| Test Notes ELF | `622f0334776a00efa858ed413ed195ee99a78fb75a2dba1d0857d67a85cc6e69` |
| Baseline serial capture | `0c13410371ceefe1814c51c2b238c87a22f457649d7983e975b1878cd84e31ce` |
| Baseline independent result | `ceb248e8e117a662e337b968ef6d1d362be5f6b9757c7f451502e37292e6485c` |
| Read-only guest image | `972f3a67012576022b67525da90c654a23b273b82cc0f1619fb6c529805ccd41` |
| QEMU executable | `986c0aac646ff3a0d8bb6eeb2090813e0d3163bc9cff0388e78397ae6a206b7e` |

The observed environment used QEMU 11.1.2, x86-64 TCG, one CPU, 512 MiB and
Qt 6.8.3. GCC/G++ 16.2.0 and Binutils 2.47.20260726 built the target artifacts.
The previous watchdog exit hang has an unresolved root cause; a joinable worker
reduces one possible teardown race but does not prove that all races are fixed.

## Resume from a fresh build directory

Configure the named variables for a matched XOS image, SDK, Qt build/source,
host Qt tools, binutils and QEMU. The build script verifies the SDK inputs and
writes a portable manifest. Use a new directory inside the repository's `build/`;
the scripts do not overwrite prior evidence.

```sh
export XOS_ROOT="$(git rev-parse --show-toplevel)"
export QEMU="$XOS_QEMU"
python3 "$XOS_ROOT/scripts/build_ssg_p3b.py" \
  --sdk "$XOS_SDK_PREFIX" --qt-build "$XOS_BUILD_DIR" \
  --qt-source "$XOS_QT_SOURCE" --host-qt "$XOS_HOST_QT" \
  --binutils "$XOS_BINUTILS" --output "$XOS_ROOT/build/p3b-repro"
python3 "$XOS_ROOT/tests/ssg_p3b_guest.py" \
  --image "$XOS_IMAGE" \
  --supervisor "$XOS_ROOT/build/p3b-repro/aggregate-test/ssg-multi.elf" \
  --browser "$XOS_ROOT/build/p3b-repro/browser-test/browser.elf" \
  --notes "$XOS_ROOT/build/p3b-repro/notes-test/notes.elf" \
  --input "$XOS_ROOT/tests/fixtures/ssg_browser/p2f.html" \
  --output "$XOS_ROOT/build/p3b-repro-baseline"
python3 "$XOS_ROOT/tests/ssg_p3b_verify.py" "$XOS_ROOT/build/p3b-repro-baseline" \
  --browser-receipt "$XOS_ROOT/build/p3b-repro/browser-test/browser.portable.receipt.json"
```

The final run still needs its own source-bound dual-provider and isolation cases,
same-boot repeated sessions, affected single-source regressions, sanitized
public evidence, and a fresh scan of actual Git blobs and the PR description.

## Later checkpoint: explicit source grants

This section records another intermediate point, not final acceptance. The
target programs were rebuilt from clean source
`59291311956c82baa2afc22a18dab308abfa87f8`; the build manifest SHA-256 was
`8f1b4b3cd871d12f9cd283d313c2e261f682eac7302e63caf273f78739815368`.
The denial verifier was strengthened separately in host-only commit `a0449bd`.
Browser and Notes text access now default to denied and require independent
`--browser-text` and `--notes-text` session grants. Real guest checks observed
default denial in the ordinary programs and independently checked the captured
test-provider responses. The source-bound dual-provider suite recorded 24
successful steps, including baseline, edit, restrictions, cross-source exit,
timeout, truncated response, cancellation and same-boot restart.

At this checkpoint a new 48-session stress run had completed 4 passing sessions;
that count is historical and does not establish its eventual result or imply
that a process continues after an interrupted turn. Raw local evidence is under
`build/p3b/v14-*`. Earlier stress runs stopped by the operator after 10/48 and
19/48 passing sessions are separately preserved and do not count toward this
build. Affected single-source guest regressions, complete evidence export and
the final public-index scan had not yet been completed at this checkpoint.
The reused SDK's full license-material check failed due to a manifest mismatch;
the old Consumer exit-race root cause remains unresolved.
