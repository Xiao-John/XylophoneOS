<!-- SPDX-License-Identifier: Apache-2.0 -->
# GNU Binutils 2.47 for XOS

This port builds the upstream GNU Binutils 2.47 release as static x86-64 ELF
programs for XOS. The build machine is arm64 macOS; the XOS host triple uses
the upstream-accepted `x86_64-unknown-elf` alias because Binutils 2.47's
`config.sub` rejects `x86_64-unknown-xos`. The output target is `x86_64-elf`.
The alias is a configure identity only; it does not add a new XOS ABI or change
the emitted ELF machine.

The release archive is fetched from GNU FTP and checked against
`source_lock.json`. Binutils uses its bundled zlib 1.3.1 source so it has no
external zlib library dependency; zstd, plugins, GDB, simulator, gprofng,
readline, NLS, and debuginfod are disabled. The linker rejects `--plugin`, `--plugin-opt`, and `--plugin-save-temps` with
explicit unsupported-option diagnostics because XOS has no dynamic loader; its
help output marks these options unsupported rather than ignored. Small port patches account for
XOS having no symlink or `lstat` support in libiberty's temporary-file helper
and no POSIX permission mode model in FatFs; executable bit updates are
omitted, with task execution governed by ELF validation in the loader. XOS
has no API for setting file timestamps, so Binutils' optional preserve-dates
copy behavior emits an explicit warning and is skipped; ordinary output
creation remains functional. The port also adds the missing final
`strdup(filename)` fallback to upstream `lrealpath`, which otherwise returns
an indeterminate value when neither `realpath` nor `canonicalize_file_name` is
available. Port patches contain XOS-authored Apache-2.0
changes alongside upstream context, which retains each source file's original
GNU license.
The matching upstream Binutils
license texts and bundled zlib license are copied without modification under
`upstream/`. New XOS build scripts and configuration are Apache-2.0; Binutils
and bundled zlib retain their upstream terms.

The build script keeps extracted source, out-of-tree objects, install files,
logs, and manifests in `.cache/xos_seed/binutils/`. It consumes a completed
`build/sdk` snapshot and records its manifest hash and the exact compiler,
configure options, source hash, patches, and installed artifact hashes.
Nothing in this port makes the generated programs runnable on the macOS host.
