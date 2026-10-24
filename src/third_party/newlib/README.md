# newlib 4.6.0 for x86_64-elf (vendored prebuilt)

Source: https://sourceware.org/pub/newlib/newlib-4.6.0.20260123.tar.gz
License: per-component; see `COPYING.NEWLIB` and source-file notices. It is not one uniform LGPL license. Archive-member source/license mapping is not completed; see `docs/licensing.md`.

Configuration used to produce `x86_64-elf/lib/libc.a` and `libm.a`:

```sh
CFLAGS_FOR_TARGET='-O2 -mno-sse -mno-sse2 -mno-mmx' \
  ../newlib-src/configure --target=x86_64-elf --prefix=... \
  --disable-multilib --disable-newlib-supplied-syscalls --disable-libgloss \
  --disable-newlib-io-long-double --disable-newlib-io-long-long \
  --disable-newlib-io-c99-formats --disable-newlib-io-pos-args
```

Note: the final prebuilt archive was produced from the **standard** build
(`-O2`, no `-mno-sse`) because newlib's libc/libm ABI uses SSE registers.
XOS E06 added per-task FXSAVE/FXRSTOR context so libc programs can use SSE.
`scripts/build_newlib.sh` records the reproducible download/build path.
