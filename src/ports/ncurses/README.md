# ncurses 6.5: bounded XOS profile

## 状态

`cross_built_guest_not_run`（2026-11-14）。宽字符终端库 + 消费者探针已交叉构建。


The ncurses 6.5 source archive and upstream COPYING notice are pinned in
`source_lock.json`. XOS can build a separate single-thread UTF-8 newlib SDK,
a static ncursesw library, matching xterm terminfo and independent consumers;
see [the plan](../../../docs/plans/ncursesw.md) and [guest acceptance](../../../docs/work_log/0187_w1_final_acceptance.md).
The recorded QEMU and GNU Screen results qualify only the tested 24x80,
single-thread serial subset. They do not establish full W1/W2, POSIX terminal,
all ncurses APIs, other terminals, dynamic resizing or threaded support. Build
and guest results must be rebound to the actual source and SDK inputs.

This directory contains source-lock and notice material, not a prebuilt or
installed target package. Use the `build_utf8_newlib.py`,
`build_utf8_sdk_candidate.py`, `probe_ncursesw.py`,
`build_ncursesw_terminfo.py`, `prepare_ncursesw_sdk.py` and guest/freeze
scripts for the isolated pipeline; their outputs and receipts define the
actual profile. The original notice is in `upstream/COPYING`, and the terminfo
source notice is retained separately. The component/member and static
redistribution review is not complete; see `licenses/components.json`.

## 构建

```sh
export XOS_SDK=/path/to/xos_sdk
export XOS_SOURCE_ARCHIVE=/path/to/ncurses-6.5.tar.gz
export XOS_OUT=/path/to/out
python3 build.py
```

配方用 autotools 交叉构建 `libncursesw.a`（`--enable-widec --without-shared
--disable-sigwinch`），生成 xterm terminfo，并交叉链接两个消费者探针
（`wide_screen_probe` 覆盖窗格/颜色/方向键/中文，`reentry_probe` 验证重入/尺寸/恢复）。

## 已知限制

- 仅验证 24x80 单线程串口子集。
- terminfo 生成可能失败。
- 不支持动态尺寸、异步信号、作业控制。

## 安装与验证

- 仅验证 24x80 单线程串口子集；不等于完整 W1/W2、POSIX 终端、全部 ncurses API。
- terminfo 生成可能失败（系统 `tic` 格式差异）；失败时 terminfo 为空，需单独用
  `scripts/build_ncursesw_terminfo.py` 生成。
- 不支持动态尺寸（SIGWINCH）、异步信号、作业控制。
- 许可审计未完成；见 `licenses/components.json`。
