# cde801a1 · glibc D1 NPTL 底层锁隐藏声明

2026-11-26 · 基线 `6dcf7fb4`。直接使用已验签 glibc 2.44 的上游规则构建
`nptl/lowlevellock.os`，重现四个 `__lll_lock_wait`、`__lll_lock_wake` 及其
`_private` 版本的隐藏别名错误。

XOS 的 `futex-internal.h` 进入上游 NPTL 实现。该路径包含 `lowlevellock-futex.h`，
而四个函数的 `libc_hidden_proto` 位于 `sysdeps/nptl/lowlevellock.h`。在实际定义所在
的上游 `nptl/lowlevellock.c` 中加入后者。该实现通过 XOS 的原生私有 wait-word 后端
执行等待和唤醒。

从 `4ff609d0` 构建普通系统和签名来源的静态 SDK。共享配置使用独立目录，沿用 D1
诊断的 `--host=x86_64-unknown-xos --enable-shared --enable-default-pie`、GCC 16.2.0、
GNU binutils 2.47 和两个构建任务。

```sh
GLIBC_BUILD="$PWD/build/lowlevellock-glibc-sdk"
SHARED_BUILD="$PWD/build/lowlevellock-shared"
python3 -B scripts/build.py --output-dir "$SYSTEM_BUILD"
python3 -B scripts/build_glibc_sdk.py --archive "$GLIBC_ARCHIVE" --output "$GLIBC_BUILD" --jobs 2
python3 -B tests/glibc_static_guest.py --system-build "$SYSTEM_BUILD" --glibc-build "$GLIBC_BUILD" \
  --suite threads --output "$GUEST_PROOF"
```

```sh
source="$GLIBC_BUILD/glibc-2.44"
mkdir "$SHARED_BUILD"
(
  cd "$SHARED_BUILD"
  export CC="$GLIBC_BUILD/cc" CXX="$GLIBC_BUILD/cxx" CFLAGS='-O2 -g -mno-red-zone'
  export LC_ALL=C CONFIG_SITE=/dev/null
  export AS=x86_64-elf-as LD=x86_64-elf-ld AR=x86_64-elf-ar NM=x86_64-elf-nm
  export RANLIB=x86_64-elf-ranlib OBJCOPY=x86_64-elf-objcopy OBJDUMP=x86_64-elf-objdump
  export READELF=x86_64-elf-readelf
  "$source/configure" --build="$(sh "$source/scripts/config.guess")" --host=x86_64-unknown-xos \
    --prefix=/usr --disable-werror --enable-shared --enable-default-pie --disable-multi-arch \
    --disable-mathvec --without-selinux --disable-nscd
  printf 'ASFLAGS += -Wa,--divide\n' > configparms
)
make -j2 -C "$source/nptl" objdir="$SHARED_BUILD" "$SHARED_BUILD/nptl/lowlevellock.os"
x86_64-elf-readelf -hW -sW "$SHARED_BUILD/nptl/lowlevellock.os"
```

## 结果

基线依赖清单中的底层锁头只有 `lowlevellock-futex.h`。修复的上游 `.os` 目标在
`build-shared = yes` 和 `build-pie-default = yes` 下生成 x86-64 `ET_REL`，四个
`__GI___lll_lock_*` 入口均为 `GLOBAL HIDDEN`。静态对象的 `.text` 与带重定位的反汇编
逐字节一致。ABI 文档表核对通过。

系统 `4a206c43da5093ac` 在 QEMU 11.1.3 运行静态 `threads` 套件三轮均通过，共十二项。
覆盖 pthread 私有同步与 TLS、主线程退出后最后工作线程收尾、detach 资源回收和
活跃线程下的有界退出。探针 ELF 解析到四个实际 `__lll_lock_*` 函数。每项退出后的
资源计数为 `129711 / 3 / 1`。

| 工件 | SHA-256 |
| --- | --- |
| 系统 manifest | `2caf73a98b1b10b4376eaed5b95678f3cfc6b536806409227d82d2e3b81f67bc` |
| 系统 ISO | `055932cadb3e54538a80067398d6c1e0c27a51b86f43e1289af6eed8fbc00e9b` |
| 已验签静态 SDK manifest | `0f818f2ab1b76269a6874602431ce1d070201b898fb26f62be6152878e510e9a` |
| `build/lowlevellock-object-evidence/base-shared-object.log` | `990b1a4b696615ae36b076c39cc3052f3cbca210e65c5469cb887d2f1f213b35` |
| `fixed-shared/nptl/lowlevellock.os` | `24ff4e0069b37fece3818ee7197ac8c5503bbc4cf057d73216f4e30f06389336` |
| 修复前后静态 `.text` | `18dc0b9a0801b43a3ee86cb698d9e523fb6e19cc4995c1a50bf1be278a99fc0e` |
| `build/lowlevellock-threads-evidence/report.json` | `6d63f6883242b89d67cea7985bf0834b1c17da5d465fa6d538b3c8a39c1809d8` |
| `build/lowlevellock-threads-evidence/serial.log` | `291565f72f322b733bf4a69b9e5c727d35aec68889e4d3d6b77bc24fbab7654e` |

`dl-execstack` 与原生动态启动仍各自验收。完整 libc 共享库和 `ld.so` 未链接或运行。
