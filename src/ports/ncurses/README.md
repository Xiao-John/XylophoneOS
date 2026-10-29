# ncursesw candidate

The 6.5 source archive and its COPYING notice are bound by `source_lock.json`.
`scripts/probe_ncursesw.py` checks the archive hash before extracting it. The
current probe does not build a usable library: XOS terminal headers, mode and
wait semantics are not yet implemented. No ncurses target binary, terminfo,
or application package is qualified or distributed by this directory.

The original notice is reproduced in `upstream/COPYING`; individual source
members and static redistribution requirements still need review for the
actual build. The project does not replace upstream terms with its own license.
