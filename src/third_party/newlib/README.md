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

### 长双精度复数的预编译库边界

2026-11-12 的 tgmath 源补丁修复类型分派，不补齐所有数学函数实现。真实的
`long double _Complex` sqrt 对象引用 `csqrtl`，当前入库的 libc.a/libm.a 都没有定义
该符号。SDK 需要对应实现及重建才能提供该调用；宿主的类型检查和实数运行不代表
完整目标 long double complex 库已可链接。审计证据见
[后续报告](../../../docs/reports/roadmap_implementation_20261112/README.md)。
