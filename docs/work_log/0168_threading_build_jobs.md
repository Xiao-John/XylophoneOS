# 0168 — Threading build parallelism

The private newlib and threaded SDK builders accept an explicit positive `--jobs` value; the default remains eight. This is a build-control change only. Argument validation was checked; a full toolchain rebuild and guest qualification were not run for this change.
