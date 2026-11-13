# lz4（上游 LZ4 1.10.0）

把 LZ4 作为纯客体包交付：命令行 `lz4`、静态库 `liblz4.a` 与公共头文件。
不进内核、不进启动镜像清单，不需要任何 OS 源码改动。

许可分两层：**库与头文件是 BSD-2-Clause，`lz4` CLI 是 GPL-2.0-only**，包内两份
文本都带（`LICENSE.library`、`COPYING.cli`）。

## 状态

`guest_verified`（2026-11-12）。上游源码零补丁；**线程化构建**（`LZ4IO_MULTITHREAD=1`），
链接线程 SDK，`-T2` 已在客体实测。

包 target profile：`xos-x86_64-static-threaded-v1`；状态词与升级条件见
[端口规范](../../../docs/ports.md)。

## 构建

配方 `build.py` 离线执行，只接受本地归档与冻结 SDK：

```sh
export XOS_SDK=/path/to/threading_sdk
export XOS_SOURCE_ARCHIVE=/path/to/lz4_1.10.0.orig.tar.gz
export XOS_OUT=/path/to/empty-output-dir
python3 src/ports/lz4/build.py
```

产出 `$XOS_OUT/thirdparty.lz4-1.10.0.xpk` 与 `$XOS_OUT/build_receipt.json`。配方先核对
归档哈希与 SDK 形状，再用 `x86_64-elf-gcc` 编译 `lib/*.c`（静态库）与 `programs/*`
（`lz4`），链接 `user.ld` + `crt0_posix.o` + `libxos/libc/libm/libgcc`。

## 安装与验证

```sh
python3 scripts/xypm.py install \
  --image work_disk.img --output-image with_lz4.img --offline \
  --profile config/package/xos_x86_64_static_threaded_v1.json \
  "$XOS_OUT/thirdparty.lz4-1.10.0.xpk"
```

已验证的包哈希：`94724be9428a9d835fe4ea6d9772be9db08c54f3f31a61af79269bcd4361c199`（788,480 字节，由本目录配方构建；换 SDK、上游或
配方后必须重算并更新 `port.json`）。

客体（xsh 直接调用，或用 `dash` 脚本）：

```text
exec-file /usr/bin/lz4 -V
    *** LZ4 command line interface 64-bits v1.10.0 ...
exec-file /usr/bin/lz4 -T2 -1 /usr/share/lz4/samples/sample.txt /sample.lz4
exec-file /usr/bin/lz4 -t /sample.lz4
    # 需要 /dev/null（#126）；基线未合并该设备时退出 1，见账本 PL-0006
    # （账本 PL-0006）；压缩/解压路径不受影响
exec-file /usr/bin/lz4 -d /sample.lz4 /sample.out
    # /sample.out 与样例逐字节相同
exec-file /usr/bin/lz4 /missing /x.lz4
    # 报错并非零退出
```

## 已知限制

- 只验证 xsh 与 dash 脚本；未跑上游 `tests/`。
- 需要线程 SDK（`build/threading_sdk`）与 threaded profile；普通 single SDK 不能构建本包。
- 安装命令必须使用 threaded profile 文件（`--profile`），否则 profile 不匹配会被拒绝。
- `-T` 的线程数上限与调度行为沿用线程 SDK 的 1:1 线程模型；SMP 未验。
- 包内头文件放在 `/usr/share/lz4/include/`（xypm 只允许 `/usr/bin`、`/usr/lib`、
  `/usr/share` 三个前缀）。
- 只构建 `lz4`，未生成 `lz4cat`/`unlz4` 链接（xypm 载荷不支持链接）。
- 源码哈希来自 Debian 镜像的 `orig.tar.gz`，未与 GitHub release 附件二次比对。
- 客体证据绑定当前基线构建与 SDK；换构建输入后需重验。
