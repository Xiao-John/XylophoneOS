<!-- SPDX-License-Identifier: Apache-2.0 -->
# 客体内编译：edit + exec-driver

发行工作盘自带交叉编译器与 sysroot，可在 `xsh>` 内改源码 → 重编 → 运行，
不需要宿主工具链。工具安装清单与验收命令见 [E08](../../e08.md)。

## 前提

- 发行盘已装：`/usr/bin/x86_64-elf-gcc`、`x86_64-elf-g++`、`/sysroot`
  （C/C++ 头与目标库）、`/src`、`/out`；以发行盘与工具链回执为准。
- `make disk` 的自建空盘没有这些工具，也没有 `dash`。
- 先 `make run` → `xos64> run` 进入 `xsh>`，见 [getting_started](getting_started.md)。

## 步骤

用行编辑器写入源码（`:wq` 保存，语法见 [edit](../supervisor/edit.md)）：

```text
edit /src/hello.c
```

保存后编译与运行（`scripts/release_smoke.py` 实测命令）：

```text
exec-driver /usr/bin/x86_64-elf-gcc -static --sysroot=/sysroot /src/hello.c -o /out/hello_c.elf
exec-file /out/hello_c.elf
```

C++ 换 `x86_64-elf-g++` 与 `.cpp` 源。预期输出 `Hello from XOS C!` 并回
`xsh>`。要点：

- 编译器启动 `cc1`/`as`/`ld` 子进程，必须用 `exec-driver` 授予直接构造权；
  普通程序运行用 `exec-file`。两命令的权限差异见
  [exec-driver](../supervisor/exec-driver.md)。
- 分步编译形式（`-c` 出 `.o` 再链接）见 [E08 客体示例](../../e08.md)。
- 改完执行 `sync`，看到 `[files] sync=ok` 再关 QEMU，见 [sync](../supervisor/sync.md)。

## 边界

- 编译失败时旧 ELF 可能仍在，不能把旧产物当成本次成功。
- `dash` 脚本与深度委派见 [dash 计划](../../plans/dash.md)；该能力不归到原发行。
- 装载上限、argv 限制与错误含义见
  [getting_started](getting_started.md) 与 [E04](../../e04_loader_sdk.md)。

## 相关

- [getting_started（宿主 SDK 主路径）](getting_started.md)
- [exec](../supervisor/exec.md)、[edit](../supervisor/edit.md)、[sync](../supervisor/sync.md)
