# jq（上游 jq 1.8.2）

把 jq 作为纯客体包交付：命令行 `jq`、静态库 `libjq.a` 与公共头文件。
不进内核、不进启动镜像清单，不需要任何 OS 源码改动。

## 状态

`guest_verified`（2026-11-12）。上游零补丁；**xsh 与 dash 两条路径都实测**。
证据见 [docs/reports/jq_1_8_2_20261112](../../../docs/reports/jq_1_8_2_20261112/README.md)。

构建配置：私有静态 **oniguruma 6.9.10**（`test/match/capture/scan/sub/gsub` 可用）、
decNumber 启用、静态、`-D_POSIX_THREADS` + 端口内单线程 pthread 桩。

状态词与升级条件见[端口规范](../../../docs/ports.md)。

## 构建

配方 `build.py` 离线执行，只接受本地归档与冻结 SDK：

```sh
export XOS_SDK=/path/to/xos_sdk
export XOS_SOURCE_ARCHIVE=/path/to/jq_1.8.2.orig.tar.gz
export XOS_ONIGURUMA_ARCHIVE=/path/to/libonig_6.9.10.orig.tar.gz
export XOS_OUT=/path/to/empty-output-dir
python3 src/ports/jq/build.py
```

产出 `$XOS_OUT/thirdparty.jq-1.8.2.xpk` 与 `$XOS_OUT/build_receipt.json`。配方先用
CMake 交叉构建私有 oniguruma 前缀，再跑 jq 的 `configure --with-oniguruma=<prefix>`，
编译 `src/*.o` 与 vendored `decNumber`，手工链接 `user.ld` + `crt0_posix.o` +
`libxos/libc/libm/libgcc` + `libonig.a`（libtool 不接受 SDK 的 crt0，故只借它生成对象）。

## 安装与验证

```sh
python3 scripts/xypm.py install \
  --image work_disk.img --output-image with_jq.img --offline \
  --profile config/package/xos_x86_64_static_single_b2_v1.json \
  "$XOS_OUT/thirdparty.jq-1.8.2.xpk"
```

已验证的包哈希：`a9696ca5e62017cf9cf0be05eb725f2ca5d74aeb512398080bfe058027518cfb`
（1,710,080 字节，由本目录配方构建；换 SDK、上游或配方后必须重算并更新 `port.json`）。

**xsh**（直接执行）：

```text
exec-file /usr/bin/jq --version
    jq-1.8.2
exec-file /usr/bin/jq -M -f /usr/share/jq/samples/filter.jq /usr/share/jq/samples/data.json
    "alpha"
    "gamma"
exec-file /usr/bin/jq -M -c .ok /usr/share/jq/samples/data.json
    true
exec-file /usr/bin/jq -M . /usr/share/jq/samples/bad.json
    jq: parse error: Unmatched '}' at line 1, column 12   （退出 5）
exec-file /usr/bin/jq -M -n -f /usr/share/jq/samples/regex.jq
    true
```

**dash**（`/tests/jq2.sh`）输出同上，并额外验证 `-n '1+1'` → `2`、`dash_rc=0`、
解析错误 `bad_rc=5`。

## 已知限制

- 正则库是**静态私有副本**，jq 包不依赖已安装的 oniguruma 包；单独使用该库请装
  [oniguruma 端口](../oniguruma/README.md)。
- decNumber 启用，数字字面量保持精确；`pthread_once`/TSS 由 SDK 的单线程 pthread 子集
  提供（本端口不再带桩）；真实多线程仍需 threaded SDK（账本 `PL-0011`）。
- 未构建 `libjq` 共享库；未跑上游 `tests/`。
- 头文件放在 `/usr/share/jq/include/`（xypm 只允许 `/usr/bin`、`/usr/lib`、`/usr/share`）。
- 源码哈希来自 Debian 镜像的 `orig.tar.gz`，未与 GitHub release 附件二次比对。
