# FatFs R0.16 (vendored)

Source: https://github.com/abbrev/fatfs `source/` (FatFs R0.16, 2025).
Copyright (C) 2025, ChaN. FatFs is distributed under the permissive FatFs
license reproduced in the header of `ff.c`/`ff.h`: source redistributions must
retain the copyright notice, condition and disclaimer; the software is provided
"AS IS" without warranty.

Local changes: `ff.c` includes `ff_string.h` instead of the host `<string.h>`;
`ffconf.h` was modified for XOS; current E08 settings use ASCII LFN/short-name aliases, code page 437, `FF_FS_NORTC=1`, no RTC/mkfs,
single volume. `diskio.c` is not used; XOS supplies `fatfs_diskio.cpp` and an ASCII-only Unicode adapter. E08 also enables static LFN workspace and object locks. Upstream notices remain intact; new XOS contributions use Apache-2.0 without replacing the FatFs terms.

0068 changes the API to UTF-8 (`FF_LFN_UNICODE=2`); XOS retains the ASCII-only OEM
short-name converter and ASCII-only case folding. Full Unicode case mapping and
non-ASCII OEM short-name conversion are not claimed.

XOS extends `FILINFO` with the sector and byte offset of the resolved SFN directory
entry. This exposes stable object location to the file service so LFN and SFN aliases
share one file identity without changing FatFs path resolution or upstream license terms.

E08-4 integration raises `FF_FS_LOCK` from 16 to 32; the file service allows
16 opens per session. Actual GCC/BFD static linking exceeded the previous 8-open
session capacity (BFD keeps at least 10 inputs cached). Limits remain bounded;
this is configuration only and does not alter upstream licensing.

2026-11-12 adds `f_rename_open(FIL*, old, new)` for the file service's shared
inode objects. It first syncs the sole backend FIL, verifies that its live lock
and directory entry match the source, then performs the existing rename and
rebinds the FIL directory pointer and lock key to the new entry. Ordinary
`f_rename` still checks and rejects open objects; `FF_FS_LOCK=32` is not disabled.
This extension is used only with the repository's serialized FAT16/FAT32
configuration, not as a general upstream API or an exFAT qualification. The
service gates further work after uncertain metadata I/O failures. The changes
are XOS Apache-2.0 contributions; original FatFs copyright/license notices are
retained. The source and header bytes are registered in `licenses/components.json`.
