# GNU gzip 1.14 for the XOS glibc SDK

This port builds the signed GNU gzip release and its bundled gnulib using the
shared [XOS/gnulib configuration](../gnulib/README.md). The source archive,
detached signature, reviewed signer fingerprint, public key and GPL text are
hash locked in `source_lock.json`. The build verifies immutable source bytes
with `gpgv` before extraction. Original source notices remain intact.

## Build and validate

Run inside the published Linux x86-64 SDK's development environment, using an
isolated source checkout and a fresh C SDK built from that checkout:

```sh
python3 scripts/build_glibc_sdk.py \
  --archive "$XOS_SOURCE_CACHE/glibc-2.44.tar.xz" \
  --output build/gzip_sdk --jobs 2
python3 scripts/create_xypm_profile.py create --runtime-family glibc \
  --sdk-build build/gzip_sdk --id xos-x86_64-glibc-gzip \
  --feature directories --feature stdio_transfer --output build/gzip_profile.json
python3 scripts/build_gnu_gzip.py \
  --archive "$XOS_SOURCE_CACHE/gzip-1.14.tar.xz" \
  --sdk build/gzip_sdk --profile build/gzip_profile.json \
  --output-dir build/gzip --jobs 2
python3 scripts/build_dash.py --sdk build/gzip_sdk/sysroot \
  --glibc-profile build/gzip_profile.json --receipt build/gzip_dash.json
python3 tests/gnu_gzip_guest.py --system-build "$XOS_SYSTEM_BUILD" \
  --gzip-build build/gzip --dash-receipt build/gzip_dash.json \
  --output build/gzip_guest
```

The gzip build writes `target/gzip`, `gnulib_consumer.elf`, GNU license material,
source-authentication output and a manifest binding the full SDK/profile, tools,
patches and configuration. `built_not_run` is intentionally distinct from guest
qualification. The guest runner verifies actual program bytes, runs them under
xsh and dash, checks error statuses/resource recovery, and reads data back only
after QEMU has stopped. Host gzip data must decode in XOS and XOS output must
decode on the host.

## Explicit profile limits

- XOS has no asynchronous POSIX signal delivery. Gzip skips its own signal
  setup/masks; no fake successful `sigaction` or `sigprocmask` is provided.
  Read/write/format errors still execute upstream output cleanup and fail.
- Directory-FD-relative path operations are unavailable. Gzip uses its existing
  full-path fallback instead of changing the process directory to emulate them.
- The libc profile cannot write file timestamps. The upstream `NO_UTIME` option
  disables filesystem timestamp copying/restoration. Gzip stream headers can
  still contain timestamps; this is not restoration of the extracted file's
  filesystem metadata. `--help` states the XOS limit.
- FAT projects fixed modes and ownership. A requested mode already matching
  `fstat` needs no mutation; a different mode fails, retains the input and removes the output.
  Ownership changes, arbitrary Unix modes and symlinks are not advertised.
- Named compression/decompression and `-c`/`-t` use the actual GNU codec and
  real XOS file/stdio operations. `-k`/`-c` keep inputs. Normal named operation
  follows upstream input-removal semantics after successful data processing.
  Shell helpers such as `zgrep` require additional tools and are not qualified.

This PR supplies source recipes and qualification, not a new binary release or
an update to the already-published prerelease assets. Any binary distribution
must ship the corresponding upstream source, these patches/recipes and the GNU
and SDK license materials.
