# SQLite for CPython on XOS

This directory pins the official SQLite 3.54.1 autoconf amalgamation and
contains an isolated static-library build. The archive is downloaded from
SQLite.org and verified by both SHA3-256 (the digest published on the official
download page) and SHA-256. SQLite's upstream copyright page states that the
SQLite source code is in the public domain; the upstream `sqlite3.c` also
contains the SQLite blessing.

The supported profile is deliberately single-threaded and single-process:

* `SQLITE_OS_OTHER=1` prevents SQLite from selecting its Unix VFS.
* `SQLITE_THREADSAFE=0` avoids a false claim of usable thread mutexes. XOS's
  custom VFS permits compatible shared locks and rejects conflicting locks
  within one process; it cannot coordinate another process or provide
  WAL/shared-memory locking.
* WAL and loadable extensions are disabled. Use rollback-journal mode.
* The VFS checks file size before each read and never seeks past EOF. FatFs
  extends a file when `f_lseek()` moves past its current end, unlike POSIX
  `lseek()`; avoiding that read pattern keeps a new zero-length database empty.
* SQLite's `xSync` and `xTruncate` call `fsync(2)` and `ftruncate(2)` through
  the C runtime. The XOS integration path wires `fsync(fd)` to the file
  service's global `sync` operation (FatFs `f_sync` plus block `CTRL_SYNC`)
  and `ftruncate(fd, size)` to the new file-service truncate operation. The
  `fsync` bridge flushes every writable open description in that service, so
  the accepted profile is single-process and guest validation must use a
  private disk with no unrelated writer. Rebuild the kernel, file service,
  libc, and SDK together before claiming the guest persistence gate passed.

## CPython integration hooks

The shared CPython builder should add this prefix's `include/` and link
`lib/libsqlite3.a` for `Modules/_sqlite/`. The extension must initialize SQLite
only after the static VFS has been linked; `sqlite3_os_init()` registers the
`xos` VFS as the default. CPython's `sqlite3.connect()` does not expose
SQLite's VFS selector, so B3 uses the registered process default. The SQLite
amalgamation and VFS must be
compiled with the same `SQLITE_OS_OTHER=1`, `SQLITE_THREADSAFE=0`,
`SQLITE_OMIT_LOAD_EXTENSION=1`, `SQLITE_OMIT_WAL=1`, and
`SQLITE_TEMP_STORE=3` definitions.

The receipt emitted by `scripts/build_cpython_sqlite.py` records source,
compiler, SDK, flags, output hashes, and the unresolved `fsync`/`ftruncate`
runtime hooks. A successful static build does not mean the guest gate passed.

## Rebuild

```sh
/usr/bin/python3 scripts/build_cpython_sqlite.py --sdk build/threading_sdk
```

All output is placed under `.cache/xos_seed/cpython/sqlite/`; this builder does
not use the shared `build/` tree.
