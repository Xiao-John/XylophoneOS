# d22a3ae3 · glibc D1 rtld 可执行栈拒绝

2026-11-26 · 基线 `39b4e51a`。使用已验签 GNU glibc 2.44 构建共享 `ld.so` 目标，
基线 `elf/dl-execstack.os` 报 `__EI__dl_make_stack_executable` 指向未定义的
`__GI__dl_make_stack_executable`。补丁 `0026` 在通用拒绝实现前配对已有
`rtld_hidden_def` 与上游 `rtld_hidden_proto`。

上游 `elf/dl-execstack.c` 的函数体直接返回 `ENOSYS`。`elf/dl-load.c:1364–1378`
遇到新增的 `PROT_EXEC` 栈要求时，仅在启动装载且 tunable 值为 1 时调用这个入口，
其余路径使用 `EINVAL`。`elf/dl-execstack-tunable.c` 的显式 force 分支在该入口拒绝后
报致命错误。`elf/Versions` 将入口登记为 `GLIBC_PRIVATE`，本补丁沿用现有别名和两个
调用点。XOS 静态原生 ELF 解析器拒绝带执行位的 `PT_GNU_STACK` 和 W+X 段，符合
[D0 权限要求](../contracts/dynamic_linking_d0.md#6-重定位保护tls-和生命周期)。

## 实际编译与策略验证

```sh
PROOF="$PWD/build/execstack-evidence/fixed"
python3 -B scripts/probe_glibc_rtld.py --archive "$GLIBC_ARCHIVE" \
  --jobs 2 --output "$PROOF"
source="$PROOF/prepared/glibc-2.44"
shared="$PROOF/shared"
static="$PROOF/prepared/configure"
make -j2 -C "$source/elf" objdir="$shared" "$shared/elf/dl-execstack.os"
make -j2 -C "$source/elf" objdir="$static" "$static/elf/dl-execstack.o"
```

从 `a40b8d29` 在断网 Linux arm64 复跑。GCC 16.2.0 和 binutils 2.47，最多两项构建。
实际 `-fPIC -DSHARED` 对象为 x86-64 `ET_REL`，`__GI__dl_make_stack_executable` 为
`GLOBAL HIDDEN`，既有名字与之同址。两个编译后的调用对象均保留指向
`_dl_make_stack_executable` 的重定位。共享、修复前静态和修复后静态对象的 `.text`
均为返回目标 `ENOSYS` 的两条指令。宿主原生 ELF 解析器在 ASan/UBSan 下通过原有
24 项和三个权限用例，分别为 NX 栈接受、EXEC 栈拒绝和 W+X 段拒绝。

## `ld.so` 的下一处依赖

干净目录的直接 `ld.so` 目标通过 execstack 对象后，依次需要 `csu` 生成的
`sem_t-align.h`、`cpu-features-offsets.h`、`features-offsets.h`、`link-defines.h` 和
`tlsdesc.h`。用上游规则生成这些文件及 `rtld-offsets.h` 后，真实重试到达两处错误。

1. `sysdeps/xos/dl-sysdep.c:5` 拒绝使用未实现的原生解释器启动。
2. `elf/dl-profile.c:387` 在 `MAP_SHARED | MAP_FILE` 处报告 `MAP_FILE` 未声明。
   该分支需要文件支持的共享可写映射来保留分析数据，当前 XOS `mmap` 只提供私有匿名保留。

本轮完成实际 `rtld.os` 与 `dl-execstack.os`，完整 `ld.so` 和客体解释器仍待验收。

| `build/execstack-evidence/` 工件 | SHA-256 |
| --- | --- |
| `base/manifest.json` | `653fd08b4841bcffb4b06996d3137b94732da1f2013a41cc334a8842844c727c` |
| `base/make_ld_so.log` | `b18f1d66af99f8d061b63929653121c939b93efdb424ee07802419ff641c55a2` |
| `fixed/manifest.json` | `16ce90a27af75699065e788abb3cf6848a00e2a7c85b38db67a333b390196113` |
| `fixed/shared/elf/dl-execstack.os` | `9ce44cb70acca5483018e4957fcd299a99afbdcd8ddaef9713286d49d631c2a5` |
| `fixed/shared/elf/rtld.os` | `1933f1e57a8a957004f16a8520c3ad1b46f22fddc327093769987fc4cd40567c` |
| 三个执行栈入口对象的 `.text` | `013f5d9b265629682a064e93f18bf734bd26d2b06fd753d96966e92cb2f315b4` |
| `objects/ld-so-after-tls-offsets.log` | `e68b5280e303f68c06b318b0c2bb9a10892e9ab57748f71d6f2bfae4f578fd2c` |
| `elf-policy.log` | `5631a0fa01bf8ea030966d109d169186d7aafba9fe17bec80981b7f59fab859f` |
