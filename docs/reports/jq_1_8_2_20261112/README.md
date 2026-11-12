# jq 1.8.2 客体证据（2026-11-12）

端口：`src/ports/jq`。本报告是 `port.json.status = guest_verified` 的证据。
只覆盖这里列出的冻结输入；换 SDK、换上游版本或改配方后必须重跑。

## 输入

| 项 | 值 |
|---|---|
| 上游归档 | `jq_1.8.2.orig.tar.gz`，sha256 `71b8d6e8f5fe81f6c6d0d110e3892251f6ce76ed095abd315e26e6e1193af3af` |
| 正则依赖 | `libonig_6.9.10.orig.tar.gz`，sha256 `ad92309d0d13eebc27f6592e875f3efbfa3dda2bf6da5952e00f0a2120c921a8`（私有静态前缀，随 jq 链接） |
| 客体系统 | 基线构建，build `82682db51a4fcdd3`，kernel 721752 字节 |
| 交叉编译器 | `x86_64-elf-gcc 16.2.0` |
| 配置 | 静态、decNumber 启用、`-D_POSIX_THREADS`、`--with-oniguruma=<private prefix>` |

## 产物

| 项 | 值 |
|---|---|
| 包 | `thirdparty.jq-1.8.2.xpk`，1,710,080 字节 |
| 包 sha256 | `a9696ca5e62017cf9cf0be05eb725f2ca5d74aeb512398080bfe058027518cfb` |
| 载荷 | `usr/bin/jq`、`usr/lib/libjq.a`、`usr/share/jq/include/{jq.h,jv.h}`、四个样例、`COPYING`、`source.json`、`build_receipt.json` |

上游零补丁，**无端口侧 shim**：jq 需要的 `pthread_once`/TSS 由 SDK 的单线程 pthread 子集
提供（`src/user/libc/pthread_single.cpp`）。

## 安装

```sh
python3 scripts/xypm.py install --image disks/base.img --output-image disks/jq4.img \
  --offline --profile config/package/xos_x86_64_static_single_b2_v1.json \
  thirdparty.jq-1.8.2.xpk
```

结果：`verify-installed = verified`；`list` 显示 `thirdparty.jq 1.8.2 rev 0`。

## xsh 路径（原始输出）

```text
xsh> exec-file /usr/bin/jq --version
jq-1.8.2
xsh> exec-file /usr/bin/jq -M -n -f /usr/share/jq/samples/regex.jq
true
xsh> exec-file /usr/bin/jq -M -f /usr/share/jq/samples/filter.jq /usr/share/jq/samples/data.json
"alpha"
"gamma"
xsh> exec-file /usr/bin/jq -M . /usr/share/jq/samples/bad.json
jq: parse error: Unmatched '}' at line 1, column 12
xsh: program exited with status 5
```

## dash 路径（原始输出）

`/tests/jq3.sh`：

```sh
/usr/bin/jq --version
/usr/bin/jq -M -n -f /usr/share/jq/samples/regex.jq
/usr/bin/jq -M -n '"x1y2" | [scan("[0-9]")]'
/usr/bin/jq -M -n '"2026-11-12" | capture("(?<y>[0-9]{4})-(?<m>[0-9]{2})")'
echo dash_rc=$?
```

```text
jq-1.8.2
true
[
  "1",
  "2"
]
{
  "y": "2026",
  "m": "11"
}
dash_rc=0
```

两条路径输出一致；带空格的过滤器只在 dash 脚本里写（xsh 不做 shell 引号处理）。

## 未覆盖

- 未跑上游 `tests/`；未构建 `libjq` 共享库；未在官方发行盘复验。
- `jq` 在串口上默认输出 ANSI 颜色（`isatty` 为真），证据统一用 `-M`。
- 正则库是 jq 私有的静态副本，jq 包不依赖已安装的 oniguruma 包。

## 复现

按 [`src/ports/jq/README.md`](../../../src/ports/jq/README.md) 设置 `XOS_SDK`、
`XOS_SOURCE_ARCHIVE`、`XOS_ONIGURUMA_ARCHIVE`、`XOS_OUT` 后执行配方，再按上面的
安装与两条路径重跑。
