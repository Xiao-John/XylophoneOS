# xxhash（上游 xxHash 0.8.3）

把 xxHash 作为纯客体包交付：命令行 `xxhsum`、静态库 `libxxhash.a` 与单头文件
`xxhash.h`。不进内核、不进启动镜像清单，不需要任何 OS 源码改动。

许可分两层，不要混写：**库与头文件是 BSD-2-Clause，`xxhsum` CLI 是 GPL-2.0-only**，
包内两份文本都带（`LICENSE.library`、`COPYING.cli`）。

## 状态

`guest_verified`（2026-11-12）。上游源码零补丁；仅新增端口侧 `compat/times.c`
（见“已知限制”）。证据见
[docs/reports/xxhash_0_8_3_20261112](../../../docs/reports/xxhash_0_8_3_20261112/README.md)。

状态词与升级条件见[端口规范](../../../docs/ports.md)。

## 构建

配方 `build.py` 离线执行，只接受本地归档与冻结 SDK：

```sh
export XOS_SDK=/path/to/xylophoneos_revival_0.0.2-1103_sdk
export XOS_SOURCE_ARCHIVE=/path/to/xxhash_0.8.3.orig.tar.gz  # sha256 见 source_lock.json
export XOS_OUT=/path/to/empty-output-dir
python3 src/ports/xxhash/build.py
```

产出 `$XOS_OUT/thirdparty.xxhash-0.8.3.xpk` 与 `$XOS_OUT/build_receipt.json`。配方先核对
归档哈希与 SDK 形状，再用 `x86_64-elf-gcc` 编译 `xxhash.c`（静态库）与 `cli/*`
（`xxhsum`），链接 `user.ld` + `crt0_posix.o` + `libxos/libc/libm/libgcc`。

## 安装与验证

```sh
python3 scripts/xypm.py install \
  --image work_disk.img --output-image with_xxhash.img --offline \
  --profile config/package/xos_x86_64_static_single_b2_v1.json \
  "$XOS_OUT/thirdparty.xxhash-0.8.3.xpk"
```

已验证的包哈希：`cbd24a96cfc6cfa26071b7286ad84431b47475230d60d8764d3b6ba536875495`
（532,480 字节，由本目录配方与 0.0.2-1103 SDK 构建；换 SDK、上游或配方后必须重算并
更新 `port.json`）。

客体（xsh 直接调用，或用 `dash` 脚本）期望值与宿主同源参考实现逐位一致：

```text
exec-file /usr/bin/xxhsum -V
    xxhsum 0.8.3 by Yann Collet
    compiled as 64-bit x86_64 + SSE2 little endian with GCC 16.2.0

exec-file /usr/bin/xxhsum -H0 /usr/share/xxhash/samples/hello.txt -> 104754c5
exec-file /usr/bin/xxhsum -H1 /usr/share/xxhash/samples/hello.txt -> 1fcb86cd080a6d68
exec-file /usr/bin/xxhsum -H2 /usr/share/xxhash/samples/hello.txt -> 62ee07f5a88eb706798eef4b08d9d85f
exec-file /usr/bin/xxhsum -H3 /usr/share/xxhash/samples/hello.txt -> XXH3_1e3102046b859e0f
```

校验模式与错误路径（dash 脚本里重定向）：

```sh
xxhsum -H1 /usr/share/xxhash/samples/hello.txt > /xxh_check.txt
xxhsum -c /xxh_check.txt          # <file>: OK，退出 0
xxhsum /missing                   # Error: Could not open '/missing': No such file or directory，退出 1
```

## 已知限制

- 只验证 xsh 与 dash 脚本两条调用路径；未跑上游 `tests/`（`make check`）套件。
- `compat/times.c` 是端口侧适配：newlib 的 `clock()` 路径需要 `times()`，而冻结 SDK
  只导出 `_times()`，故转发一次。上游文件未改。
- 包内 `xxhash.h` 放在 `/usr/share/xxhash/include/`（xypm 只允许 `/usr/bin`、`/usr/lib`、
  `/usr/share` 三个前缀），开发者在客体里编译需自行加该 include 路径。
- 只构建 `xxhsum`，未生成 `xxh32sum`/`xxh64sum`/`xxh128sum`/`xxh3sum` 符号链接（xypm
  载荷不支持链接）。
- 源码哈希来自 Debian 镜像的 `orig.tar.gz`（`sha256_scope: mirror_fetch`），未与
  GitHub 发布页附件二次比对。
- 客体证据绑定系统 build `0d9e4e844e51f7b5` 与 0.0.2-1103 SDK；换构建输入后需重验。
