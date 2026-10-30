# SSG-P1: cross-process, prewired, read-only experiment

The qualification JSON and compressed raw guest logs in this directory are the
source of the results. This is an experiment with one GUI provider and one
independent consumer connected by a spawn-authorized parent, not a general
broker, arbitrary-process discovery, per-message identity, remote revocation or
production authorization. The console records what the consumer received; the
actual requests and replies flow through the two guest pipes.

The test disk contains synthetic data only. QEMU PS/2 key events edit/scroll the
real Notes/Browser UI; the consumer parses the real replies and records each
JSON frame. The `03-resp.json`, `04-resp.json`, and `05-resp.json` Notes frames
are respectively the initial document snapshot, the edit diff and the next
snapshot; `qualification.json` gives the exact hashes of every recorded frame.
Browser frame numbers may vary if a capped snapshot requires bounded resync.
The display/geometry scope and security limits are in
[the SSG-P1 contract](../../contracts/ssg_p1_pipe.md).

The final combined run reports **17 scoped top-level checks passed**. In that
run the kernel recorded Notes parent/provider/consumer PIDs `10/12/11`, and
Browser parent/provider/consumer PIDs `37/39/38`; [process-identity.json](process-identity.json)
also records their distinct address spaces and parent-child start events. These
records corroborate the topology but do not authenticate each message.
The guest resource counters were `[130279 free pages, 2 tasks, 0 completions]`
before the display service and returned to the same tuple after all sessions;
each session also returned to the intermediate display-service baseline
`[130235, 3, 1]` before the next began.

The real Notes document node had bounds `[242,148,508,357]`. A guest keyboard
event changed its prefix from `Visible note title` to `aVisible note title`,
and the consumer observed scene version 3 → 4. The following hashes are over
the exact JSON payload bytes received by the consumer:

| Payload | SHA-256 |
|---|---|
| [Initial snapshot](03-resp.json) | `00706b90bf465d7f009cd9491d5c86257807422a05acf5ba19dbb7ddaa0e9171` |
| [Edit diff](04-resp.json) | `c54c76c0b70b36d1605370b4bb6076315619251724825c6098f1fc76a2dd3415` |
| [Changed snapshot](05-resp.json) | `38a7274b530bf1180cb550c72296634650318c2816ec629231c1963217b33a71` |

`reconstructed-wire/` adds the deterministically reconstructed 12-byte frame
headers to those payloads. The consumer validated the incoming magic, length
and sequence; these files are reconstructed from those fields, not a separate
raw packet capture. [wire-manifest.json](wire-manifest.json) hashes them.

The original pipe probe passed 12 xsh checks and observed the expected dash
spawn denial. The existing SceneStream diff fixture passed 12 checks in each
shell, and the existing application-local Notes regression passed five checks.
The real Qt security fixture passed 27 native checks and five guest-level checks.
The current ABI/document checks passed. A license audit against the image
manifest failed in this stacked worktree because the manifest names a Desktop
source absent from this branch. The image-source worktree passed its seven
registered-material checks, and the 13 changed/new source files were separately
checked for Apache-2.0 SPDX identifiers. Two test sources in that image-source
worktree differ from its frozen manifest; this is not a full static Qt
distribution/member/relink license review. Both audit outcomes are retained.

**A larger-page Browser regression did not pass.** Two runs of this branch's
Browser and one run of the earlier frozen Browser, on the same image and test,
all returned capped snapshots and `RESET_REQUIRED` at the scroll-diff assertion.
Both candidates passed the preceding document/layout and link-hit checks. The
[comparison](regressions/browser-comparison.json) and all three raw logs are
retained; the cause is not established. The cross-process Browser test above
passed on its smaller explicitly bounded page. Do not extrapolate that result
to complete larger documents or rebind the old Browser qualification.

## Reproduce with the prepared local SDK

Run from the SSG-P1 worktree; choose a **new** output directory. These paths
identify the prepared Qt 6.8.3/SDK inputs used on this machine. The scripts
validate the SDK manifest and pinned Browser source, and write full build
commands, input hashes and artifact hashes; no downloads or host app changes are
performed by these commands.

```sh
python3 scripts/build_ssg_p1.py \
  --sdk ../XylophoneOS-qt6-e17/build/qt_e17/sdk \
  --qt-build ../XylophoneOS-qt6-e17/build/qt_e17/widgets \
  --qt-source ../XylophoneOS-qt6-e17/build/qt_e17/qtbase \
  --host-qt ../XylophoneOS-qt6-e15/build/qt_e15/host-install \
  --binutils ../XylophoneOS-qt6-e17/.cache/xos_seed/threading_sdk_tools \
  --output build/ssg-p1-reproduce

QEMU=../runtime/qemu-prefix/opt/qemu/bin/qemu-system-x86_64 \
python3 tests/ssg_ipc_guest.py \
  --image ../XylophoneOS-aurora-glass/build/aurora_glass/system-v5/xos.img \
  --session build/ssg-p1-reproduce/session.elf \
  --consumer build/ssg-p1-reproduce/consumer/ssg-consumer.elf \
  --notes build/ssg-p1-reproduce/notes/notes.elf \
  --browser build/ssg-p1-reproduce/browser/browser.elf \
  --dash ../XylophoneOS-dash-c1-c3/build/dash_c3_frozen/dash.elf \
  --output build/ssg-p1-reproduce/guest
```

The guest runner creates a dedicated disposable FAT disk and launches these
commands through `exec-driver`, which delegates the parent's spawn authority:

```text
exec-driver /bin/session.elf /ssg.txt scenario --text
exec-driver /bin/session.elf /web/ssg.html browser-scenario --browser --text
```

The parent spawns `/bin/ssg-consumer.elf` and either `/bin/notes.elf` or
`/bin/browser.elf`, passing a fresh instance value and the two pipe routes.
It does not give either child spawn authority. Ordinary interactive examples
are `detail document --text`, `diff document 5 --text`, and `watch document 5
--text` after `/ssg.txt` in the same session command. The GUI stays open until
closed normally; the parent waits for both processes. Without `--text`, Notes
returns metadata without text and Browser's text-bearing provider denies the
query. The consumer's own console output can contain authorized document text.

## Failure evidence retained

- `initial-failure/` preserves the first real guest run: `BAD_FRAME`, a Qt
  `QThread::start` resource error, and no successful cross-process scene. Qt
  diagnostics sharing the pipe were a likely cause of frame corruption; the
  original log did not capture the invalid header bytes. Later builds route Qt
  diagnostics to the console and use one GUI timer rather than another provider
  watchdog thread.
- `harness-failure/` preserves a later run in which the test checked the prefix
  of a still-incomplete status line. The preceding consumer checks passed, but
  the harness exited before the normal termination check. The harness now waits
  for the entire status marker.
- `browser-capped-run/` preserves the actual capped Browser snapshot and the
  resulting `RESET_REQUIRED` diff. The earlier acceptance script incorrectly
  expected an immediately complete snapshot. The consumer now makes a bounded,
  paced resync and only accepts an actual complete diff. The passing final run
  did not trigger that retry branch, so recovery after a cap remains NOT_RUN.
- `protected-fixture/` is a **separate synthetic but real Qt widget fixture**,
  not a fake Notes/Browser tree. Its recorded local SSG checks cover password
  redaction, inherited `xosSsgProtected` redaction, node destruction and the
  existing local Intent regression. This fixture is not a cross-process password
  qualification or production policy service.

The verbatim generic transport probe and runner in this branch were originally
introduced in upstream Draft [#30](https://github.com/Xiao-John/XylophoneOS/pull/30),
commit `91233bb72cc02dbc9cca805042def40712682dc2`. Its rerun is recorded separately:
rewiring a running owned child is rejected, and the dash child without delegated
spawn rights is denied. Neither result establishes a generic unrelated-peer
connection or revocation facility.
