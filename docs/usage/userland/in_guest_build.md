<!-- SPDX-License-Identifier: Apache-2.0 -->
# 客体内编译：edit + exec-driver

发行工作盘自带交叉编译器与 sysroot，可在 `xsh>` 内改源码 → 重编 → 运行，
不需要宿主工具链。工具安装清单与验收命令见 [E08](../../e08.md)。

| 方式 | 编译在哪里 | 适用 | 文档 |
|---|---|---|---|
| 客体内建 GCC（本页） | XOS 内 `/usr/bin/x86_64-elf-gcc` | 盘上现场改源码重编、验证客体工具链 | 本页 |
| 宿主 SDK `compile.py` | 宿主 `x86_64-elf-gcc/g++` | 日常开发、批量构建 | [getting_started](getting_started.md) |
| 宿主打包成 XPK | 客体不可打包；宿主 `xos_app.py` | 要分发/安装的应用 | [xpk_packages](xpk_packages.md) |

## 前提

- 发行盘已装：`/usr/bin/x86_64-elf-gcc`、`x86_64-elf-g++`、`cpp`、
  `/usr/libexec/gcc/x86_64-elf/16.2.0/{cc1,cc1plus,collect2}`、
  `/sysroot`（C/C++ 头与目标库）、`/src`、`/out`；以发行盘与工具链回执为准。
- `make disk` 的自建空盘没有这些工具；空盘也没有 xypm、python3（实测发行
  工作盘才有 `/usr/bin/xypm`、`/sysroot`、`/usr/bin/python3`）。
- 先 `make run` → `xos64> run` 进入 `xsh>`，见 [getting_started](getting_started.md)。
- 磁盘改完要 `sync`；QEMU 正开着时宿主不能 import 同一张盘。

## 全链步骤：edit → 保存 → exec-driver → exec-file → sync

1) 进编辑器写入源码（行编辑器语法见 [edit](../supervisor/edit.md)；正文行不走
分词器，只有 `:` 开头的行是编辑器命令）：

```text
edit /src/hello.c
```

2) `:wq` 保存退出（`:w` 只保存；`:q` 未保存会提示）。

3) 编译（`scripts/release_smoke.py`、`docs/e08.md` 实测命令；编译器会创建
`cc1`/`as`/`ld` 子进程，**必须用 `exec-driver`**，别名 `exd`）：

```text
exec-driver /usr/bin/x86_64-elf-gcc -static --sysroot=/sysroot /src/hello.c -o /out/hello_c.elf
```

C++ 换 `x86_64-elf-g++` 与 `.cpp` 源。分步编译（先 `-c` 出 `.o` 再链接）：

```text
exec-driver /usr/bin/x86_64-elf-gcc --sysroot=/sysroot -I/src -c /src/main.c -o /out/main.o
exec-driver /usr/bin/x86_64-elf-gcc -static --sysroot=/sysroot /out/main.o -o /out/app.elf
exec-file /out/app.elf
```

4) 运行（普通程序用 `exec-file`，不授予构造权）：

```text
exec-file /out/hello_c.elf
```

预期输出 `Hello from XOS C!` 并回 `xsh>`。成功默认只显示程序输出；非零退出、
故障、取消仍可见，`trace on` 可看 `[wait] pid=… kind=exited code=N`。

5) 落盘：

```text
sync
```

看到 `[files] sync=ok` 再关 QEMU；否则重启后内容可能丢失。见
[sync](../supervisor/sync.md)。

6)（可选）在脚本里连做多步：

```text
dash /out/build.sh
```

`dash script.sh` 从 xsh 取得深度 2 的受限委派，可再驱动 GCC/G++；而
`exec-driver dash script.sh` 只有深度 1，脚本内再调 GCC 会明确 `EPERM`
（[exec-driver](../supervisor/exec-driver.md)）。`make -B -f /out/project.mk all`
也是已验收入口（`release_smoke.py`、C3 报告）。能力边界见 [dash](dash.md)。

## 与宿主交叉编译的对比

| 维度 | 客体 `edit` + `exec-driver` | 宿主 `compile.py` / `xos_app.py` |
|---|---|---|
| 前提 | 发行盘工具与 `/sysroot`；空盘没有 | `x86_64-elf-gcc` 在 `PATH` 或 `XOS_CC`/`XOS_CXX`；发行 SDK 含 `compile.py` |
| 输入 | 盘上 `/src` 的文件（`edit` 或宿主 `work_disk.py import`） | 仓库外项目目录 / 任意宿主路径 |
| 编译命令 | `exec-driver /usr/bin/x86_64-elf-gcc -static --sysroot=/sysroot <src> -o <out>` | `python3 "$SDK/compile.py" --c hello.c -o hello.elf` |
| 运行 | `exec-file /out/hello.elf` | 先 import 到盘再 `exec-file` |
| 产物持久化 | 必须 `sync` | 宿主文件天然持久，客体侧仍需 `sync` |
| 速度/资源 | 单核 TCG、8 任务、65536 页/任务上限，慢 | 宿主原生速度 |
| 打包 | 不支持；XPK 只能在宿主打 | `xos_app.py init/build/check/pack`，见 [xpk_packages](xpk_packages.md) |
| 典型场景 | 客体上现场修一行重编、验证客体工具链本身 | 日常开发、CI、发版 |

**何时用客体开发**：要验证的就是客体工具链/系统本身（E08、`make`、dash 脚本
构建链）、或手头只有客体终端。**何时用宿主交叉编译**：日常迭代、要出 XPK、
要复现回执与确定性产物；两者都产出静态 ELF64/x86-64，但**结果不是同一回执**
，不能互相冒充（[packages 计划](../../plans/packages.md)：SDK 交叉构建、客体
原生构建、可安装包是三个独立结果）。

## 客体里能不能用 xypm

- **查询可以**：发行盘实测有 `/usr/bin/xypm` 与 `/var/lib/xypm/db.json`，
  `xypm list`、`xypm info <id>`、`xypm verify <file.xpk>` 在 `xsh>` 与
  `dash` 下都可用（`tests/package_p1_guest.py`）。
- **写入要维护会话**：`maint-run /usr/bin/xypm install|upgrade|remove ...`，
  且必须回到 `xsh>` 执行；详见 [maintenance](../supervisor/maintenance.md) 与
  [xpk_packages](xpk_packages.md)。
- **客体不能打 XPK**：`xos_app.py`/`xypm.py` 是宿主 Python 工具，客体没有
  打包器；不确定的组合（如在自建空盘上用 xypm）以实际回执/`--help` 为准。
- 本地改的源码若要分发，仍走宿主打包，不要把客体临时 ELF 当包内容。

## 失败排查

| 现象 | 原因与处理 |
|---|---|
| `xsh: cannot <阶段>: <路径> (error=N)` 或找不到命令 | 路径不存在/不是可装载 ELF；空盘没有 `/usr/bin/x86_64-elf-gcc`；`ls`/`type` 核对，先确认启动的是发行盘 |
| 用 `exec-file` 跑编译器 | 编译器需要直接构造权启动 `cc1`/`as`/`ld`；改用 `exec-driver`（或从 `dash script.sh`/`make` 走已验收委派）。具体报错以实测为准 |
| 编译报缺头文件/`fatal error: ... No such file` | 忘了 `--sysroot=/sysroot`，或源码不在 `/src`；对齐上面命令。诊断分段（`compile`/`link`/`source_or_include_lookup`）可参考 `scripts/seed_diagnostics.py`，它自己标注 `classification_is_hint` |
| 编译报语法错误、未定义符号、非法选项 | 真实失败：`bad_header.c`、`bad_syntax.c`、`undefined_link.c`、非法 `-truncate` 四条负路径在 E08 R5 均以非零退出（`tests/e08_post5_p1.py`）；看 `kind=exited code=N` |
| 旧 ELF 还在、结果像没变 | 编译失败时旧产物可能仍在；不能把旧 ELF 当本次成功，先删或换输出名再编 |
| 权限/资源拒绝（`busy or denied`、构造失败） | 有其他应用在跑或资源不足；退出无关程序、`trace on` 看阶段；满盘在维护事务中表现为 `transaction stopped` + `maintenance: retained`（`tests/package_p2_full_disk.py`），普通编译的磁盘满具体报错以实测为准 |
| 空间/配额 | 单任务 65536 页、每会话 16 打开、全局 32 FatFs 锁；`stats`/`ls` 核对，必要时清理 `/out` 后 `sync` |
| 改完重启内容没了 | 忘 `sync`；看到 `[files] sync=ok` 再关 QEMU |
| 宿主导入失败 `FatFs error=8` | 目标已存在；先关 QEMU，换文件名（[getting_started](getting_started.md)） |

## 边界

- 只覆盖受限静态配置：不声称完整 POSIX、动态链接、线程并发、编译器自举、
  系统重建或任意掉电（[E08 限制](../../e08.md)）。
- 装载上限、argv 限制与错误含义见 [getting_started](getting_started.md)
  与 [E04](../../e04_loader_sdk.md)。
- 脚本、管道与作业控制的资格边界见 [dash](dash.md)。

## 相关

- [getting_started（宿主 SDK 主路径）](getting_started.md)、
  [xpk_packages（XPK 分发）](xpk_packages.md)、[dash（脚本入口）](dash.md)
- 命令：[exec](../supervisor/exec.md)、[exec-driver](../supervisor/exec-driver.md)、
  [exec-file](../supervisor/exec-file.md)、[edit](../supervisor/edit.md)、
  [ls](../supervisor/ls.md)、[sync](../supervisor/sync.md)、
  [stats](../supervisor/stats.md)
- 机制：[E08 原生工具链](../../e08.md)、[E04 装载与 SDK 契约](../../e04_loader_sdk.md)
- 索引：[命令使用手册](../index.md)
