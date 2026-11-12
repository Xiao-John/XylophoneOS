# Oniguruma 6.9.10 客体证据（2026-11-12）

端口：`src/ports/oniguruma`。本报告是 `port.json.status = guest_verified` 的证据。

## 输入

| 项 | 值 |
|---|---|
| 上游归档 | `libonig_6.9.10.orig.tar.gz`，sha256 `ad92309d0d13eebc27f6592e875f3efbfa3dda2bf6da5952e00f0a2120c921a8`（Debian 镜像） |
| 客体系统 | 基线构建，build `82682db51a4fcdd3`，kernel 721752 字节 |
| 交叉编译器 | `x86_64-elf-gcc 16.2.0` |
| 构建 | CMake 交叉构建（`CMAKE_SYSTEM_NAME=Generic`、静态库） |

## 产物

| 项 | 值 |
|---|---|
| 包 | `thirdparty.oniguruma-6.9.10.xpk`，包 sha256 `7be31e58ec623f1feb64ba0fd5da1761586a425a5d404f124ab252d847f0a23b` |
| 载荷 | `usr/lib/libonig.a`、`usr/share/oniguruma/include/{oniguruma,oniggnu,onigposix}.h`、`samples/regex.c`、`COPYING`、`source.json`、`build_receipt.json` |

## 安装

```sh
python3 scripts/xypm.py install --image disks/base.img --output-image disks/onig.img \
  --offline --profile config/package/xos_x86_64_static_single_b2_v1.json \
  thirdparty.oniguruma-6.9.10.xpk
```

结果：`verify-installed = verified`。

## 客体验收（探针为包内自带样例编译）

`regex.c`：`onig_new("a(b+)c")` 匹配 `"xxabbbcyy"`。

```text
xsh> exec-file /tests/regex
start=2 end=7 groups=2
ONIG_OK
```

dash 路径：

```text
dash /tests/onig.sh
start=2 end=7 groups=2
ONIG_OK
dash_rc=0
```

## 未覆盖

- 只测 UTF-8 + 默认语法；其它编码/语法、posix 接口、上游 `tests/` 未跑。

## 复现

按 [`src/ports/oniguruma/README.md`](../../../src/ports/oniguruma/README.md) 构建与安装，
再用包内 `samples/regex.c` 编译探针导入工作盘运行。
