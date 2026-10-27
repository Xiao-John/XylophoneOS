# sbase subset for XOS

Pinned sbase source supplies the provenance and MIT license for the small
`cat`, `cp`, `mkdir`, `mv`, and `rm` ports. XOS adaptations intentionally keep
only regular-file and same-volume behavior supported by the current runtime.
There is no recursive remove/copy, permission-bit preservation, symlink, or
cross-filesystem fallback. Build explicitly with `scripts/build_sbase.py`;
ordinary system builds do not download or install these programs.

Daily utility development uses `daily_utilities.json` and
`scripts/build_daily_utilities.py`, which build 13 independent DU1/DU2
candidates against an explicitly chosen SDK. The older five-tool builder and
its receipts are unchanged. New `ls`, `rmdir`, `head`, `tail`, `wc`, `tee`,
`basename` and `dirname` sources are XOS-authored Apache-2.0; the five older
sbase adaptations retain MIT with later XOS changes under Apache-2.0. The
manifest records intended subsets, not guest acceptance or package support.
`tail` limits retained content to 1 MiB, `ls` limits directory listings to
4096 entries/1 MiB, and `wc` counts words with ASCII whitespace. File
metadata, recursive operations and full POSIX behavior are not claimed.
