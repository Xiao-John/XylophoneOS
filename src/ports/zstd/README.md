# zstd（上游 Zstandard 1.5.7）

把 Zstandard 作为纯客体包交付：命令行 `zstd`、静态库 `libzstd.a` 与三个公共头文件。
不进内核、不进启动镜像清单，不需要任何 OS 源码改动。

许可：上游双许可，本包同时携带 `LICENSE`（BSD-3-Clause）与 `COPYING`（GPLv2）。

## 状态

`guest_verified`（2026-11-12）。上游零补丁；**xsh 与 dash 两条路径都实测**。
证据见
[docs/reports/zstd_1_5_7_20261112](../../../docs/reports/zstd_1_5_7_20261112/README.md)。

构建配置：**线程化**（`ZSTD_MULTITHREAD`）、`ZSTD_LEGACY_SUPPORT=0`、`ZSTD_NOTRACE`；
链接线程 SDK，`-T2` 已在客体实测。

状态词与升级条件见[端口规范](../../../docs/ports.md)。

## 构建

配方 `build.py` 离线执行，只接受本地归档与冻结 SDK：

```sh
export XOS_SDK=/path/to/threading_sdk
export XOS_SOURCE_ARCHIVE=/path/to/libzstd_1.5.7+dfsg.orig.tar.xz
export XOS_OUT=/path/to/empty-output-dir
python3 src/ports/zstd/build.py
```

产出 `$XOS_OUT/thirdparty.zstd-1.5.7.xpk` 与 `$XOS_OUT/build_receipt.json`。库用上游
`lib/Makefile` 构建（`CC/AR/RANLIB` 指向交叉工具），CLI 手工编译并链接
`user.ld` + `crt0_posix.o` + `libxos/libc/libm/libgcc`。

## 安装与验证

```sh
python3 scripts/xypm.py install \
  --image work_disk.img --output-image with_zstd.img --offline \
  --profile config/package/xos_x86_64_static_threaded_v1.json \
  "$XOS_OUT/thirdparty.zstd-1.5.7.xpk"
```

包 target profile：`xos-x86_64-static-threaded-v1`。已验证的包哈希：`039a38f762278a0f7d20a7bd2d33173e31710fbe50c7bb37091b335ce5a58624`
（2,437,120 字节，由本目录配方构建；换 SDK、上游或配方后必须重算并更新 `port.json`）。

**xsh**（直接执行）：

```text
exec-file /usr/bin/zstd --version
    *** Zstandard CLI (64-bit) v1.5.7, by Yann Collet ***
exec-file /usr/bin/zstd -1 -f /usr/share/zstd/samples/sample.txt -o /xsh.zst
    /usr/share/zstd/samples/sample.txt :  5.95%   (  3.93 KiB =>    239 B, /xsh.zst)
exec-file /usr/bin/zstd -t /xsh.zst
    /xsh.zst            : 4020 bytes
exec-file /usr/bin/zstd -d -f /xsh.zst -o /xsh.out
    /xsh.zst            : 4020 bytes
```

**dash**（`/tests/zstd.sh`）输出同上，并额外覆盖 `-19`、`-t`、缺失文件
（`zstd: can't stat /missing ...`，`missing_rc=1`）与各步退出码。

## 已知限制

- 需要线程 SDK 与 threaded profile；`-T` 已用 2 线程验证，SMP 未验。
- `ZSTD_LEGACY_SUPPORT=0`：不能解压旧版（v0.1–v0.7）帧。
- 未跑上游 `tests/`；未构建 `zstdmt`/`zstdgrep` 等包装脚本。
- 头文件放在 `/usr/share/zstd/include/`（xypm 只允许 `/usr/bin`、`/usr/lib`、`/usr/share`）。
- 源码哈希来自 Debian 镜像的 `orig.tar.xz`，未与 GitHub release 附件二次比对。
