# sbase subset for XOS

Pinned sbase source supplies the provenance and MIT license for the small
`cat`, `cp`, `mkdir`, `mv`, and `rm` ports. XOS adaptations intentionally keep
only regular-file and same-volume behavior supported by the current runtime.
There is no recursive remove/copy, permission-bit preservation, symlink, or
cross-filesystem fallback. Build explicitly with `scripts/build_sbase.py`;
ordinary system builds do not download or install these programs.
