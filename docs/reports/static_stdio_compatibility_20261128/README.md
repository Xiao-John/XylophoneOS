# Strict compatibility for ordinary static standard streams

The actual patched static loader passed **45 checks in three native guest
rounds**, including **12 executions of real SDK-built target ELFs**. Every round
restored exactly **129779 free pages / 2 tasks / 0 completions**. A file used in
the rejected Files-inheritance cases retained its bytes after shutdown and an
offline FAT readback.

## Composition and observed behavior

The code and fixture checkpoint is
`bddaf0fa4650beaacaa5094acca9def6c02e09e2`. The native SDK, CRT, kernel and services
come from production source `3699916df590a2fe0ea9b419836ded2d9344e6b3`, native build
`c1575e2adfc6fa5d`. The builder copies and verifies that complete SDK, then
explicitly compiles the new production `src/user/loader/load.cpp` before linking
SDK archives. The old archive loader is therefore not substituted for the
implementation under test. The loader source SHA is
`6c67569169ab3dca4b84d7650c0345024dc632ca4649da51e08bbf42db816486`; the actual
probe ELF is
`19c92eccf996154f2f9f5720985fb68c070753fbae3e1f92c35ebbf59c8001cc`.

The strict target compiler used the actual Preview 2 cross compiler with
`-Werror -Wconversion -Wshadow`, the bound native SDK headers/linker script/CRT,
and no hosted C++ runtime. Actual ELF section inspection confirmed that the raw
target has no `.xos.exec` section and that both marker-bearing targets have one.

| Checks in each round | Actual result |
|---|---|
| Raw static ELF with ordinary kernel standard streams | Runs, receives startup v2 |
| ELF with valid v3 marker | Runs, retains startup v3 |
| Raw ELF with explicitly closed stdin | Runs, read returns denied |
| Raw ELF with real pipe input and aliased stdout/stderr | Reads `DATA`, writes `OUTERR`, endpoints close |
| Extra fd, unsupported status flags, route mismatch | Unsupported at inspect |
| Duplicate fd, inconsistent alias object | Unsupported at inspect |
| Same-process replacement, existing invalid marker | Unsupported at inspect |
| Actual Files stdout, legacy file-handle transfer | Unsupported at inspect |
| CLOEXEC-only cleanup record | Unsupported at inspect |
| Pinned bootstrap entry with null prepare callback | Unsupported at inspect; no legacy fallback |

The raw static target is
`dec9344353d5d681d69e18a512f1c87005a178be3ddc9880214d3ccf2c91f61b`.
The correct-v3 target is
`01539322692e230961789cf15a24229635c2fb07a7c0d348bfc5a1753499b03b`.
The wrong-version marker target is
`c60f86989b396015ae707e279e312fe4f4f6290a09cb01d0a79d58316ff54385`.

All negative cases require the real loader's inspect-stage diagnostic and native
unsupported result. No loader, Files, pipe or kernel behavior is modeled. The
supervisor checks the global resource baseline after each complete probe, using
its existing authority. The probe itself has ordinary child-creation authority.

## Reproduction and evidence

Run inside the Preview 2 SDK with new output directories:

```sh
python3 scripts/build_static_stdio_probe.py \
  --system "${XOS_NATIVE_SOURCE}/build/system" \
  --system-source "${XOS_NATIVE_SOURCE}" \
  --output build/static_stdio_probe_v4
python3 tests/static_stdio_compat_guest.py \
  --system "${XOS_NATIVE_SOURCE}/build/system" \
  --system-source "${XOS_NATIVE_SOURCE}" \
  --fixture build/static_stdio_probe_v4 --repeat 3 \
  --output build/static_stdio_guest_v3
```

`fixture_build.json` retains built/not-run status; `guest_report.json` records
the actual execution. `source_binding.json` independently checks all 14 explicitly
recorded builder, fixture, loader and runner input files against their immutable
Git blobs and the unchanged source hashes captured before and after execution.
`system_manifest.json` retains the original native source and artifact inventory.
Serial and per-round transcripts contain the actual ordered markers and exits.

The initial failed compiler attempt and both failed guest attempts are retained.
The compiler failure was an unsupported initializer-list expression in the test
fixture without the corresponding hosted header; an explicit array fixed it.
Both initial guest attempts passed the four positive launches, then stopped
because the fixture wrongly tried a supervisor-only resource-statistics syscall
from an ordinary process. The final fixture removes that incorrect assumption
and keeps the real outer supervisor resource checks. The production loader bytes
did not change between those guest attempts. These failed attempts are not
counted as completed qualification.

All published records are derived exports. `conversion.json` records the
unpublished original byte identities and exact path/text transformations. Only
the flat root `manifest.json` hashes exported leaves.

## Boundary of this qualification

The correction restores only standard streams that the existing v2 kernel routes
can express exactly. It does not discard extra FDs or Files ownership, grant
creation authority, relax exec replacement, or allow dynamic pinned bootstraps
to bypass their format contract. See
[the compatibility contract](../../contracts/static_stdio_compatibility.md).

This is the actual new loader paired with the stated existing native system. It
does not claim that a newly rebuilt complete SDK/system or the installer gate
has already passed. The final integrated build must still exercise its ordinary
external raw-native program through glibc spawn, alongside the independently
corrected GNU constructor/READY path.
