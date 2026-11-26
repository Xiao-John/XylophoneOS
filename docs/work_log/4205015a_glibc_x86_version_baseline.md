# 4205015a · glibc x86-64 字符串符号版本

主线 `cb14678a` 从签名核验通过的 glibc 2.44 原包构建共享归档。构建
已越过 `fstatfs` 与 `lseek64`，在 `string/memmove.os` 处因
`ABI_libc_GLIBC_2_2_5` 缺失而失败，make 返回 2。上游 x86-64 汇编用该
标识判断历史 `memcpy` 兼容版本是否启用。XOS 的实验共享 ABI 从 `GLIBC_2.44`
起步。现有版本生成规则已经归并了其它已登记但早于基线的版本。

XOS x86-64 版本描述以空版本节登记这一历史标识，供上游生成器归并。
生成的 `abi-versions.h` 将 `ABI_libc_GLIBC_2_2_5` 和
`VERSION_libc_GLIBC_2_2_5` 分别指向基线编号和名称。完整 `libc.map`
与改前逐字节相同。实际 `memmove.os` 使用 `memcpy@@GLIBC_2.44`，无
`memcpy@GLIBC_2.2.5` 项。静态 `memmove.o` 的 `.text` 前后逐字节一致。
[实验版本边界](../contracts/dynamic_linking_d0.md#4-依赖闭包搜索与输入预算)

改后再次构建整个 `libc_pic.a`，成功编译 `memmove.os`，首次失败推进至
`sysdeps/xos/open.c` 的 `__libc_open` 别名。完整共享归档和解释器仍待构建。

## 可复验命令

两轮均使用 Linux arm64、GCC 16.2.0、binutils 2.47 和只读签名归档。
分别在 `cb14678a` 和已发布的 `0966a905` 的独立工作树中执行以下命令。`GLIBC_ARCHIVE`
指向同一份原始归档，同目录保留分离签名。`PROOF` 每轮使用新的绝对路径，基线和
修复后的路径分别记为 `BASE_PROOF` 和 `SELECTED_PROOF`。

```sh
python3 scripts/probe_glibc_rtld.py --archive "$GLIBC_ARCHIVE" --jobs 1 --output "$PROOF"
SOURCE="$PROOF/prepared/glibc-2.44"
SHARED="$PROOF/shared"
STATIC="$PROOF/prepared/configure"
make -j1 -C "$SOURCE/string" objdir="$STATIC" "$STATIC/string/memmove.o"
x86_64-elf-objcopy -O binary --only-section=.text "$STATIC/string/memmove.o" "$PROOF/memmove.text"
make -j1 -C "$SOURCE/string" objdir="$SHARED" "$SHARED/string/memmove.os" \
  >"$PROOF/memmove-shared.log" 2>&1
```

最后一条命令在基线返回 2，并在日志保留缺失的版本标识。修复后的同一命令
返回 0。两轮结束后比较实际生成的映射和静态代码，并检查修复后的 ELF。

```sh
cmp "$BASE_PROOF/shared/libc.map" "$SELECTED_PROOF/shared/libc.map"
cmp "$BASE_PROOF/memmove.text" "$SELECTED_PROOF/memmove.text"
x86_64-elf-readelf -hWs "$SELECTED_PROOF/shared/string/memmove.os"
```

| 工件 | SHA-256 |
| --- | --- |
| 选中源码的签名核验回执 | `79a10fb644fe71c44c3192fc71662e115e45dcb97a0af4bfd13e5e69351d0b8d` |
| 生成的 `abi-versions.h` | `97bdb05561a01ef4bd2f3dce7e111c6a8b6e44ba336b1976aae77c6273c89f9f` |
| 两轮相同的 `libc.map` | `b0c7b741fa19ee08e7c4cea567191a7ed5adf0780ec109896cb7447149d316ae` |
| 目标 `memmove.os` | `cafbc3ffe686ea5adcddb89f131a3d5f613443529cba132af36d60491f3341e2` |
| 目标 ELF 符号记录 | `0719ae51b884a45e4ee3d77336ad8979a76029dbd79db45914721f507a3044ab` |
| 前后相同的静态代码 | `037d3530cb4ccf9dd37fdfb8aa50d51e6a70915dbc742b2d0fa6c3bee05a9640` |
| 共享归档复验日志 | `03a8b25a623bc86586f60f7c4dd38c2e73e67a589b7010ea23a7d35ecba195c1` |
