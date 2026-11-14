# ncursesw 6.5: bounded XOS profile

The ncurses 6.5 source archive and upstream COPYING notice are pinned in
`source_lock.json`. XOS can build a separate single-thread UTF-8 newlib SDK,
a static ncursesw library, matching xterm terminfo and independent consumers;
see [the plan](../../../docs/plans/ncursesw.md) and [guest acceptance](../../../docs/work_log/0187_w1_final_acceptance.md).
The recorded QEMU and GNU Screen results qualify only the tested 24x80,
single-thread serial subset. They do not establish full W1/W2, POSIX terminal,
all ncurses APIs, other terminals, dynamic resizing or threaded support. Build
and guest results must be rebound to the actual source and SDK inputs.

This directory contains source-lock and notice material, not a prebuilt or
installed target package. Use the `build_utf8_newlib.py`,
`build_utf8_sdk_candidate.py`, `probe_ncursesw.py`,
`build_ncursesw_terminfo.py`, `prepare_ncursesw_sdk.py` and guest/freeze
scripts for the isolated pipeline; their outputs and receipts define the
actual profile. The original notice is in `upstream/COPYING`, and the terminfo
source notice is retained separately. The component/member and static
redistribution review is not complete; see `licenses/components.json`.
