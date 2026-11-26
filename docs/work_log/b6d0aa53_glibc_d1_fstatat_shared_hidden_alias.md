# b6d0aa53 · glibc D1 fstatat 共享别名

2026-11-26 · 基线 `e33ef656`。独立复跑 glibc 2.44 的 `io/fstatat.os`，重现
`__EI___fstatat` 指向未定义 `__GI___fstatat`。同一份上游 `include/sys/stat.h`
声明 `__fstatat`，其隐藏声明列出 `__fstatat64`。XOS 原有实现以
`libc_hidden_def(__fstatat)` 收尾，因此在实现前加相应的 `libc_hidden_proto`。
现有静态配置中此宏为空，公开 `fstatat` 继续由上游弱别名机制提供。

在 `e0f1f63b` 构建静态 SDK，使用同一份已验签归档、原生 sysdeps、GCC 16.2.0 和
GNU binutils 2.47。共享配置在独立目录中执行。文件套件覆盖 `fstatat` 路径查询、
`AT_EMPTY_PATH` 描述符查询及普通描述符下相对路径的 `ENOTSUP`，在应用已有文件
会话上执行。

```sh
python3 -B scripts/build.py --output-dir "$SYSTEM_BUILD"
python3 -B scripts/build_glibc_sdk.py --archive "$GLIBC_ARCHIVE" --output "$GLIBC_BUILD" --jobs 2
python3 -B tests/glibc_static_guest.py --system-build "$SYSTEM_BUILD" --glibc-build "$GLIBC_BUILD" \
  --suite files --output "$GUEST_PROOF"
```

对共享对象使用 Linux 构建环境中的配套 `x86_64-elf` 工具，从新目录执行上游规则。

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
make -j2 -C "$source/io" objdir="$SHARED_BUILD" "$SHARED_BUILD/io/fstatat.os"
x86_64-elf-readelf -hW -sW "$SHARED_BUILD/io/fstatat.os"
```

## 结果

共享配置选择 `build-shared = yes` 和 `build-pie-default = yes`。真正的上游
`io/fstatat.os` 规则使用 `-fPIC -DSHARED`，产物为 x86-64 `ET_REL`。`readelf` 看到
`__GI___fstatat` 为 `GLOBAL HIDDEN`，公开 `fstatat` 为 `WEAK DEFAULT`。修复前后静态
`io/fstatat.o` 的 `.text` 字节与包含重定位的反汇编均相同。

QEMU 11.1.3 使用系统 `27c1103be4df644a` 和同源静态 SDK。单线程文件、多线程文件和
exec 继承三种调用各运行三次，九项均成功。前两种各执行新增的三个 `fstatat` 检查。
客体 ELF 的 `__fstatat` 与公开 `fstatat` 位于同一地址，退出后资源均回到
`129711 / 3 / 1`。ABI 文档表核对通过。

| 工件 | SHA-256 |
| --- | --- |
| 系统 manifest | `1045b31aef8abba9e391256ad70c37d216de6e843f374a74e6b2dca27c99fa56` |
| 系统 ISO | `0f30587d4782b6456a39688d4082f4ff211f0c4e4df549a85512fbb3d99f7436` |
| 已验签静态 SDK manifest | `58584522c7937fa196d727769645219998a9ff4214ebe4a34001fe987894f699` |
| `build/fstatat-object-evidence/base-shared-object.log` | `61a2763287eb725d7e60d258bd632f049f5426847ad310c814b9026e193f6d31` |
| `fixed-shared/io/fstatat.os` | `fed733ec1d3d565dfeec3accb73b5abe4e9110a17c323ea6db5f8f7b3ef47b41` |
| 修复前后静态 `.text` | `6becc02a6777157eccc9b523bd594ce98bc720ccff8787e1e03e886ae43a1522` |
| `build/fstatat-files-evidence/report.json` | `f0ab84bf6d623beb0b2c80775c187f3b01bb2b454bc3444b497244554d948c3e` |
| `build/fstatat-files-evidence/serial.log` | `26eb2b61f8824b9898ffb99d3294a87afbe01ef7ce6ffea5dba48d39a1c80ff7` |

完整共享 libc 和 `ld.so` 仍待链接验证。NPTL 和动态启动保留独立验收。
