# Zstandard 1.5.7 客体证据（2026-11-12）

端口：`src/ports/zstd`。本报告是 `port.json.status = guest_verified` 的证据。

## 输入

| 项 | 值 |
|---|---|
| 上游归档 | `libzstd_1.5.7+dfsg.orig.tar.xz`，sha256 `0c092ef267edce57ba7f3f2645c861f72eaf5e76273c6c3632869423464b90a5`（Debian 镜像） |
| 客体系统 | 基线构建，build `82682db51a4fcdd3`，kernel 721752 字节 |
| 交叉编译器 | `x86_64-elf-gcc 16.2.0` |
| 配置 | 线程化（`ZSTD_MULTITHREAD`）、legacy 关闭、`ZSTD_NOTRACE` |
| 构建 SDK | `build/threading_sdk`（profile `xos-x86_64-static-threaded-v1`） |
| 参考实现 | 宿主 `zstd 1.5.7`（同版本，用于对拍字节） |

## 产物

| 项 | 值 |
|---|---|
| 包 | `thirdparty.zstd-1.5.7.xpk`，2,437,120 字节 |
| 包 sha256 | `039a38f762278a0f7d20a7bd2d33173e31710fbe50c7bb37091b335ce5a58624` |
| 载荷 | `usr/bin/zstd`、`usr/lib/libzstd.a`、`usr/share/zstd/include/{zstd,zdict,zstd_errors}.h`、样例、`LICENSE`+`COPYING`、`source.json`、`build_receipt.json` |

## 安装

```sh
python3 scripts/xypm.py install --image disks/base.img --output-image disks/zstd.img \
  --offline --profile config/package/xos_x86_64_static_threaded_v1.json \
  thirdparty.zstd-1.5.7.xpk
```

结果：`verify-installed = verified`。

## 客体运行（xsh 与 dash 原始输出）

样例 `usr/share/zstd/samples/sample.txt`：4020 字节，sha256
`9456d918b200e98f7deececc237f7aa748d80a7da8951a27b2509a84dd04c009`。

```text
zstd --version                      -> *** Zstandard CLI (64-bit) v1.5.7, by Yann Collet ***
zstd -T2 -1 -f -o /sample.zst sample.txt -> 3.93 KiB => 239 B (5.95%)
zstd -t /sample.zst                  -> /sample.zst : 4020 bytes   (test_rc=0)
zstd -d -f /sample.zst -o /sample.out-> /sample.zst : 4020 bytes   (dec_rc=0)
zstd -19 -f sample.txt -o /sample19.zst -> 3.93 KiB => 180 B (4.48%) (c19_rc=0)
zstd /missing                        -> can't stat /missing ... (missing_rc=1)
```

- `/sample.out` 与 `/xsh.out` 都与原件逐字节相同（sha256 `9456d918…`）。
- 客体产出的 `/sample.zst`（239 B）sha256 `5f21b1d5ebade438096934bd1afd927cabc8c49b111c9e185858a3251abccfc9`，
  与宿主同版本 `zstd -1` 的输出**完全相同**；宿主 `zstd -d` 能解压客体产物并还原原文件。

xsh 路径直接执行同一组命令（`-1`/`-t`/`-d`），输出与 dash 一致。

## 未覆盖

- 上游 `tests/` 未跑；`-T2` 已验证压缩/解压与宿主互解，SMP 未验；不能解压 legacy 帧。
- 未在官方发行盘复验。

## 复现

按 [`src/ports/zstd/README.md`](../../../src/ports/zstd/README.md) 设置 `XOS_SDK`、
`XOS_SOURCE_ARCHIVE`、`XOS_OUT` 后执行配方，再按上面的安装与命令重跑；宿主同版本
`zstd -1` 可用于对拍压缩字节。
