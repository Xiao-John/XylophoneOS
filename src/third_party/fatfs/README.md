# FatFs R0.16 (vendored)

Source: https://github.com/abbrev/fatfs `source/` (FatFs R0.16, 2025).
Copyright (C) 2025, ChaN. FatFs is distributed under the permissive FatFs
license reproduced in the header of `ff.c`/`ff.h`: source redistributions must
retain the copyright notice, condition and disclaimer; the software is provided
"AS IS" without warranty.

Local changes: `ff.c` includes `ff_string.h` instead of the host `<string.h>`;
`ffconf.h` is set to 8.3 names, code page 437, `FF_FS_NORTC=1`, no LFN/RTC/mkfs,
single volume. `diskio.c` is not used; XOS supplies `fatfs_diskio.cpp`.
