# XOS Make：显式重建的串行子集

本端口选择 sbase 提交 `c546c3a5724c81cee9a11d816a38ccdf17472129` 中的真实 Make，
不是 GNU Make。源码和适配已准备；本文初始状态为 **未构建、未客体验收**。
只有独立 C3 客体报告通过后，才能把对应条目记录为通过。

XOS 当前没有可用于 Make 的真实修改时间。这个 profile 要求显式 `-B`（也可由
显式 MAKEFLAGS 继承），启动时打印说明：时间戳不可用，所有带 recipe 的目标
每次重建。它保留真实依赖顺序、源文件存在性和失败状态，不提供增量构建。
没有用伪造时间或宿主执行替代客体行为。

## 选定行为

- 显式目标及 prerequisites，串行 recipe；同一进程内共享依赖只构建一次，环依赖
  明确失败。没有 recipe 的既有源文件作为输入；缺失且无规则的输入失败。
- 原解析器的 `NAME = value`、命令行赋值、`$(NAME)` / `${NAME}`、`$$`、include
  和行续接。命令行变量按原优先级覆盖 Makefile 变量；没有声明 GNU 扩展兼容。
- `$@` 为目标，`$<` 为第一个显式 prerequisite；`$?` 依赖修改时间，明确拒绝。
- `@`、`-` recipe 前缀及 `-i/-s/-k/-S/-e/-p/-d` 的选定原实现；普通 recipe
  的 `-n` 打印而不执行。`+` 前缀明确拒绝，避免 dry-run 隐式启动递归命令。
- `-f file`、默认 `makefile` / `Makefile`；缺失文件明确失败。
- 默认且本 profile 唯一接受的 Shell 是 `/usr/bin/dash`。每行启动独立 Shell，
  使用真实 `fork → execve → waitpid`，分别以 `-ec` 或忽略错误时的 `-c` 执行。

普通 recipe 失败会令 Make 非零退出；显式忽略错误可继续后续 recipe。Escape
或被强制终止/故障的 recipe 退出会令 Make 退出 137，不能被 `-i`、`-` 或
`.IGNORE` 吞掉。当前 wait ABI 将强制取消和故障都报告为 SIGKILL，诊断同时列明
这些可能原因，不把故障误报为已证实的键盘取消。失败或取消时保留部分产物并提示；
不承诺自动删除残缺目标。

## 明确排除

无 `-B` 请求、`-j/-q/-t/-r`、未知选项和不支持的 MAKEFLAGS 请求均失败。
禁用默认/后缀/模式推导与 `.DEFAULT`；非空 `.SUFFIXES` 和 `%` 模式目标/依赖
明确失败。没有并行 jobserver、mtime 增量判断、touch、异步用户态信号处理、
完整 GNU Make 函数或任意外部 Shell 兼容保证。

当前进程总数、fork 深度、256 字节单参数和环境大小仍受 XOS ABI 限制；过长
recipe 或耗尽进程资源会明确失败。Make 需要受限构造深度 2，recipe Dash 保留
该深度，然后可将深度 1 委派给 GNU driver。此权限由启动方的明确 profile 授予，
Make 不自行提升权限。

## 待执行的客体例子

```make
CC = /usr/bin/x86_64-elf-gcc
CFLAGS = --sysroot=/sysroot -static

all: /out/hello.elf

/out/hello.elf: /src/hello.c
	$(CC) $(CFLAGS) $< -o $@
```

```text
dash /tests/run_make.sh
# run_make.sh 内：make -B -f /tests/Makefile all
```

正式验收需保存选定源码/SDK/ELF 摘要、工具版本、QEMU 命令和真实输出，覆盖
实际 C/C++ 编译及运行、第二次调用仍重建、菱形依赖一次执行、依赖环、失败/忽略
错误、dry-run 无产物、缺文件/不支持选项、Escape 后资源回基线，以及真实构建
脚本消费端。宿主 Make/Shell 对照仅提供预期语义，不能算 XOS 功能证据。

终止状态137在此profile中保留：包括recipe Shell转递其外部任务的SIGKILL/fault
状态，即使-i/-/.IGNORE也停止Make。显式`exit 137`同样停止，不承诺完整POSIX
ignore行为；这条规则避免中间Shell把终止转换成普通退出后掩盖实际失败。

## 最终真实资格（2026-10-26）

C3主专项66项通过，包含真实C/G++项目、坏源/修复、重复-B、各负例/取消与匿名
生命周期；还由XOS内真实GCC/G++编译该Make源码，运行其产物重建项目，并以
显式exec执行自建Make验证同PID及权限3→2。具体输入、输出、状态、配置/工具、
SDK/ELF SHA与资源计数在docs/reports/dash_c3_20261026/。
旧GNU工具普通console编译已验证；未知CRT的文件stdio继承明确拒绝。不要把该
profile宣称为GNU Make、增量构建、异步信号或所有旧静态ABI兼容。
