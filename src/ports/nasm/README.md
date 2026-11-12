# nasm（上游 NASM 2.16.03）

把 NASM 作为纯客体程序交付：产物打成 `.xpk`，由 xypm 安装到工作盘，在客体里汇编。
不进内核、不进启动镜像清单，不需要任何 OS 源码改动。

## 状态

`guest_verified`（2026-11-12）。零源码补丁；上游 `configure` 的交叉探测直接适配
冻结 SDK 的 libc 面。证据见
[docs/reports/nasm_2_16_03_20261112](../../../docs/reports/nasm_2_16_03_20261112/README.md)。

状态词与升级条件见[端口规范](../../../docs/ports.md)。

## 构建

配方 `build.py` 离线执行，只接受本地归档与冻结 SDK：

```sh
export XOS_SDK=/path/to/xylophoneos_revival_0.0.2-1103_sdk
export XOS_SOURCE_ARCHIVE=/path/to/nasm-2.16.03.tar.xz   # sha256 见 source_lock.json
export XOS_OUT=/path/to/empty-output-dir
python3 src/ports/nasm/build.py
```

产出 `$XOS_OUT/thirdparty.nasm-2.16.03.xpk` 与 `$XOS_OUT/build_receipt.json`。
配方先核对归档哈希与 SDK 形状，再跑上游 `configure --host=x86_64-elf`，链接
`user.ld` + `crt0_posix.o` + `libxos.a/libc.a/libm.a/libgcc.a`，最后 `--strip-all` 并打包。

## 安装与验证

```sh
python3 scripts/xypm.py install \
  --image work_disk.img --output-image with_nasm.img --offline \
  --profile config/package/xos_x86_64_static_single_b2_v1.json \
  "$XOS_OUT/thirdparty.nasm-2.16.03.xpk"
```

已验证的包哈希：`0b7940222df8c08fe76ccb289b7117b35fd7690afe52cbf05825416a54a88d11`（1,730,560 字节，由本目录配方与 0.0.2-1103 SDK 构建；
换 SDK、上游或配方后必须重算并更新 `port.json`）。

客体（xsh）：

```text
exec-file /usr/bin/nasm -v
    NASM version 2.16.03 compiled on ...
exec-file /usr/bin/nasm -f bin /usr/share/nasm/hello.asm -o /hello.bin
    # 期望 6 字节：b8 34 12 cd 10 f4
exec-file /usr/bin/nasm -f elf64 /usr/share/nasm/macro64.asm -o /macro64.o
    # 期望 x86-64 REL，_start 处 b8 3c 00 00 00 / bf 00 00 00 00 / 0f 05 / 90 90
```

错误路径（应打印 `nasm: fatal: unable to open input file ...` 并以状态 1 退出）：

```text
exec-file /usr/bin/nasm /nonexistent.asm -o /x.bin
```

## 已知限制

- 只验证 xsh 调用；dash 路径未测。
- 未跑 NASM 自带 `test/` 测试套件；只做了 `-v`、`-h`、`-f bin`、`-f elf64`（含
  `%macro`/`%rep`）与错误路径的针对性样例。
- 只构建 `nasm`，未构建 `ndisasm`。
- 源码哈希来自 BLFS 镜像（`sha256_scope: mirror_fetch`），未与 nasm.us 官方哈希二次比对。
- 客体证据绑定系统 build `0d9e4e844e51f7b5` 与 0.0.2-1103 SDK；换构建输入后需重验。
