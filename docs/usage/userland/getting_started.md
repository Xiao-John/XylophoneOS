<!-- SPDX-License-Identifier: Apache-2.0 -->
# 用户态程序开发上手

从零写一个 hello、编译、放进工作盘并在 `xsh>` 跑起来的最短路径。面向宿主侧
开发；两条编译方式与适用场景：

| 方式 | 编译在哪里 | 适用 | 文档 |
|---|---|---|---|
| 宿主 SDK `compile.py` | 宿主 `x86_64-elf-gcc/g++` | 日常开发，本页主线 | 本页 |
| 客体内建 GCC | XOS 内 `/usr/bin/x86_64-elf-gcc` | 盘上现场改源码重编 | [in_guest_build](in_guest_build.md) |

机制与 ABI 见 [E04 装载/SDK 契约](../../e04_loader_sdk.md)、[E08 原生工具链](../../e08.md)；
独立项目与发行细节见[快速开始](../../friend_user_program_quickstart.md)。

## 环境前提

| 前提 | 说明 |
|---|---|
| python3、nasm、QEMU | `make` 变量 `PYTHON`/`NASM`/`QEMU` 可覆盖；缺 QEMU 时 `run_qemu.py` 直接报错退出 |
| 仓库根执行 | 下文命令均在仓库根目录运行 |
| `make build` | 生成 `build/` 镜像、用户态程序与中间 SDK `build/sdk/`（头、CRT、库、`user.ld`、manifest；**不含** `compile.py`） |
| `make disk` | 显式创建 `work_disk.img`（默认 2 GiB FAT32）；已存在则不改动 |
| 发行 SDK | `build/releases/<版本>/xylophoneos_revival_<版本>_sdk/`，内含 `compile.py` 与 `examples/hello.c`、`hello.cpp`；也可用发行 tar 包解压目录 |
| 交叉工具链 | 宿主编译需 `x86_64-elf-gcc`/`x86_64-elf-g++` 在 `PATH`，或用 `XOS_CC`/`XOS_CXX` 指定 |

各脚本参数以 `--help` 实测为准，下文为摘要。

## 第一步：先跑通现成的 hello（不写代码）

```sh
make disk     # 已有 work_disk.img 时跳过
make run
```

`make run` 依赖 `install-iso`（`build`+`dash`）后执行
`python3 scripts/run_qemu.py --install-iso`；串口输出直接显示在当前终端。
缺盘时脚本报 `Work disk missing; run 'make disk' once, or pass --work-disk`。

启动后在串口依次输入：

```text
xos64> run
xsh> exec-file hello.elf
```

应打印 `hello from file` 并回到 `xsh>`。`hello.elf` 是 files 服务首次启动时从
内置 `hello` 引导模块写入工作盘的（已有则提示 `[files] hello.elf present`），
无需任何编译。内置引导模块也可用 `exec hello` 启动（见 [exec](../supervisor/exec.md)）。

## 第二步：写最小 hello

C（发行示例 `examples/hello.c`）：

```c
/* SPDX-License-Identifier: Apache-2.0 */
#include <stdio.h>
int main(void) { puts("Hello from XOS C!"); return 0; }
```

C++（发行示例 `examples/hello.cpp`）：

```cpp
/* SPDX-License-Identifier: Apache-2.0 */
#include <cstdio>
#include <string>
int main() { std::string s("Hello from XOS C++!"); std::puts(s.c_str()); return 0; }
```

普通程序写 `main` 即可，不必写底层 `xos_user_main`；`compile.py` 自动选择
CRT、链接脚本与静态库。仓库内参考实现：`src/user/programs/hello.cpp`
（`xos::sdk` 接口）与 `src/user/programs/libc_hello.cpp`（newlib `printf`）。

## 第三步：编译（发行 SDK 的 `compile.py`）

`compile.py` 随发行 SDK 打包（`scripts/package_release.py` 写入），与 SDK 同
目录；仓库 `build/sdk/` 是 `make build` 的中间产物，没有该文件。实测
`--help`（以脚本为准）：

```text
usage: compile.py [-h] -o OUTPUT [--c] sources [sources ...]
```

| 参数 | 含义 |
|---|---|
| `sources...` | 一个或多个 `.c`/`.cpp` 源文件 |
| `-o` / `--output` | 必填，输出 ELF 路径 |
| `--c` | 按 C 编译；省略则按 C++ |

编译命令（`$SDK` 替换为发行 SDK 目录）：

```sh
python3 "$SDK/compile.py" --c hello.c -o hello.elf      # C
python3 "$SDK/compile.py" hello.cpp -o hello.elf        # C++
```

两例实测均产出 `ELF 64-bit LSB executable, x86-64, statically linked`。
线程 SDK 是另一套 `compile.py`（`src/user/threading/compile.py`），参数不同，
见 [threads](../../implementation/threads.md)。

## 第四步：放进工作盘

`scripts/work_disk.py` 是宿主离线文件桥（首次会用 `clang++`/`c++` 编译
`scripts/work_disk_host.cpp` 到 `build/work_disk_host`）。实测参数（以
`--help` 为准）：

```text
usage: work_disk.py [-h] image {mkdir,import,export} path [source]
```

先关闭使用该盘的 QEMU，再执行：

```sh
python3 scripts/work_disk.py work_disk.img mkdir /out
python3 scripts/work_disk.py work_disk.img import /out/hello.elf hello.elf
```

- `path` 必须是客体绝对路径，不能含 `.`/`..` 分量。
- `import` 拒绝覆盖：重复导入同一路径报 `FatFs error=8` 并以非零退出；
  重测换新文件名或新盘副本。
- 发行盘已有 `/out`、`/src`；`make disk` 的新盘为空，需先 `mkdir`。

## 第五步：运行

```sh
make run
```

随后在串口：

```text
xos64> run
xsh> ls /out
xsh> exec-file /out/hello.elf
```

- `run` 单向进入 supervisor，不返回内核控制台，回到 `xos64>` 只能重启
  QEMU，见 [run](../kernel/run.md)；约 1 秒无输入会自动停旧演示任务。
- 成功时默认只显示程序输出（`Hello from XOS C!`）；`trace on` 可见
  `[wait] pid=… kind=exited code=0` 等诊断；非零退出、故障与取消仍会显示。
- 需要构造子进程的程序（编译器等）用 `exec-driver`（别名 `exd`），普通
  hello 用 `exec-file`，见 [exec-file](../supervisor/exec-file.md)、
  [exec-driver](../supervisor/exec-driver.md)。
- 改文件或装入新程序后执行 `sync`，看到 `[files] sync=ok` 再关 QEMU，
  见 [sync](../supervisor/sync.md)。
- 前台等待时单独按 Escape 取消被等待任务；Ctrl-C 关闭宿主 QEMU。

## 日志位置

| 来源 | 位置 |
|---|---|
| `make run` 串口输出 | 直接显示在终端（QEMU `-serial stdio`），不落盘 |
| 测试 QEMU | `build/<名称>_qemu.log`、`build/<名称>_serial.log`（`tests/boot_smoke.py` 写入） |
| 发行冒烟 | `build/releases/<版本>/package_serial.log`、`package_failed_serial.log`、`package_smoke_report.json`（`scripts/release_smoke.py` 写入） |
| 客体内程序输出与文件 | 输出走串口即终端；持久文件在 `work_disk.img`，需 `sync` |

## 常见错误

| 现象 | 原因与处理 |
|---|---|
| `Work disk missing; run 'make disk' once, or pass --work-disk` | 尚无工作盘；`make disk` 一次即可，已有盘不会被覆盖 |
| `Run make build first` | 缺镜像；先 `make build` |
| import 报 `FatFs error=8` | 目标路径已存在；换名字或新盘副本，`import` 不覆盖 |
| `xsh: cannot <阶段>: <路径> (error=N)` 或 `xsh: <路径>: …` | 装载失败（路径、ELF 校验、资源）；`trace on` 查看 stage 与格式细节 |
| 找不到 `x86_64-elf-gcc` | 安装交叉工具链或设置 `XOS_CC`/`XOS_CXX`；以 `compile.py --help` 为准 |
| 用 `exec-file` 跑编译器失败 | 编译器启动 `cc1`/`as`/`ld` 需要直接构造权，必须 `exec-driver`，见 [E08](../../e08.md) |
| 宿主编出的程序不能跑 | 只接受静态 ELF64/x86-64；动态链接、`PT_INTERP` 等在装载时拒绝 |
| 找不到刚导入的文件 | 先关 QEMU 再导入；`ls` 核对；构建成功不等于已安装 |
| 重复 import 或编辑冲突 | `import` 拒绝覆盖；`edit` 不承诺冲突检测，改后 `sync` 再核对 |

## 相关

- 机制：[E04 装载与 SDK 契约](../../e04_loader_sdk.md)、[E08 原生工具链](../../e08.md)
- 命令：[exec-file](../supervisor/exec-file.md)、[exec-driver](../supervisor/exec-driver.md)、
  [edit](../supervisor/edit.md)、[ls](../supervisor/ls.md)、[sync](../supervisor/sync.md)
- 索引：[命令使用手册](../index.md)；发行/独立项目见[快速开始](../../friend_user_program_quickstart.md)
