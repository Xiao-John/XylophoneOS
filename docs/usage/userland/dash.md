<!-- SPDX-License-Identifier: Apache-2.0 -->
# dash 使用（发行盘上的可选 Shell）

dash 是 XOS 的**可选**用户态 Shell（0.5.13.5 移植），安装为 `/usr/bin/dash`；
Xsh（`xsh>`）仍是默认入口，不创建 `/bin/sh` 别名、不替换默认 Shell。资格范围见
[Shell 实现（C1–C3 已验收）](../../implementation/shell.md)与
[C3 资格报告](../../reports/dash_c3_20261026/qualification.json)（`status: passed`，
`scope: declared bounded foreground XOS profile; not full POSIX`）。

## dash 从哪里来

| 方式 | 说明 | 依据 |
|---|---|---|
| install ISO 首启安装 | files 服务启动时若 ISO 携带 dash payload 且 `/usr/bin/dash` 不存在，就写入该路径；**已存在则直接返回（保留旧文件）** | `src/user/services/file_ui.cpp` 的 `install_boot_dash`；`docs/reports/dash_c3_20261026/iso_dash_install_report.json` |
| `make run` | 依赖 `install-iso`（`build`+`dash`+`build_install_iso.py`），默认从 install ISO 启动，因此新盘首启即可获得 dash | `Makefile`、`docs/usage/index.md` |
| 手动补装旧盘 | `python3 scripts/install_dash.py --disk <disk> [--path /usr/bin/dash] [--manifest <dash/manifest.json>]`（参数以 `--help` 为准） | `scripts/install_dash.py` |
| 构建本身 | `make dash`（= `python3 scripts/build_dash.py --sdk build/sdk`），产出绑定 source lock/patch 与匹配 SDK 的 ELF 清单 | `Makefile`、`src/ports/dash/README.md` |

边界：

- `make disk` 只创建工作盘，**不预装** dash（`disk:` 目标只跑 `make_work_disk.py`）。
- 发行工作盘镜像实测**不含** `/usr/bin/dash`（`release_smoke.py` 断言
  `fresh_work_disk_has_no_dash`）；它只由 ISO 首启安装。
- 不是编译程序的必经入口：`exec-driver`/`exec-file`、`make` 都能独立工作。

## 写第一个 .sh

脚本是工作盘上的普通文本文件，ASCII 路径；Xsh **不会**把不认识的文件自动当
Shell 脚本执行（[xsh](../../xsh.md)），必须显式交给 dash。

方式 A——宿主写好再导入（先关 QEMU）：

```sh
python3 scripts/work_disk.py work_disk.img mkdir /out
python3 scripts/work_disk.py work_disk.img import /out/hello.sh hello.sh
```

方式 B——客体内用行编辑器：`edit /out/hello.sh`，正文行不走分词器，`:wq`
保存，见 [edit](../supervisor/edit.md)。改完 `sync`，看到 `[files] sync=ok`
再关 QEMU。

最小脚本（来自 `tests`/`scripts/release_smoke.py` 的实测形态，可直接照抄）：

```sh
set -e
value=$(printf 'one\ntwo\n' | cat)
cat <<'EOF' > /out/heredoc.txt
ISO_C3_HEREDOC
EOF
echo RELEASE_DASH_C3_OK
```

## 执行方式

```text
xsh> dash /out/hello.sh
xsh> dash -i
xsh> sync
```

| 入口 | 行为 |
|---|---|
| `dash /path/script.sh` | 从 xsh 以裸命令运行脚本；`tests/dash_*_smoke.py`、`daily_utilities_*`、`release_smoke.py` 全部用这一形式 |
| `dash -i` | 切入可选 dash 交互，退出后回 xsh（`shell_smoke_report.json` 的 `interactive_returns_to_xshell`） |
| `exec-driver dash /path/script.sh` | 深度 1：dash 能启动普通子程序，**不能再委派给 GCC**，会明确 `EPERM`；需要在脚本里编译时不要用这个入口（见 [exec-driver](../supervisor/exec-driver.md)） |
| `exec-file script.sh` | 不执行：脚本必须显式交给 dash，不认识的文件不自动当脚本 |

`release_smoke.py` 实测样例（在发行盘上）：

```text
dash /out/c_stage.sh            → RELEASE_DASH_C3_OK
make -B -f /out/project.mk all  → Hello from XOS C!
xypm info python_idna           → id: python_idna
```

## 与 xsh 内建的分工

| 需求 | 用什么 |
|---|---|
| 查看/装载/维护/文件管理：`help` `type` `trace` `ps` `kill` `images` `exec` `spawn` `wait` `stats` `maint-*` `primtest` `elftest` `ls` `cat` `stat` `rm` `edit` `filetest` `sync` `exec-file` `exec-driver` `spawn-file` `mkdir` `mv` | xsh 内建，只在 `xsh>` 生效 |
| 管道、重定向、命令替换、here-doc、循环/条件、函数、多命令串 | dash（xsh 按空格分词，**不支持**引号、管道、重定向） |
| 写文件后落盘 | 两个 Shell 都要 `xsh>` 的 `sync`（dash 里没有该内建） |
| 包安装事务 | 必须回 `xsh>` 用 `maint-run`（dash 是普通用户进程，满足不了"没有其他应用"） |
| 编译 | `xsh>` 下 `exec-driver /usr/bin/x86_64-elf-gcc ...`，或 `dash script.sh`（深度 2，可再委派 GCC），或 `make -B -f <mk> all`；见 [in_guest_build](in_guest_build.md) |

裸命令按 `/usr/bin:/bin:/` 有序 PATH 搜索，所以 `dash`、`xypm`、`make` 都能
直接敲；含斜杠的路径只检查该路径本身（[xsh](../../xsh.md)）。

## C1–C3 能力边界（已验收范围）

| 维度 | 当前支持 | 不支持 / 未验收 |
|---|---|---|
| 前台流水线 | 最多 **4 段**；全部启动后阻塞等待；第 5 段在执行前拒绝（退出 2） | 更长流水线、后台管道 |
| 进程 | 真实单线程 fork 隔离，**fork 深度 3**；全局 8 个进程 | 线程 profile 的 fork/exec；任意压力 |
| 重定向 | `<` `>` `>>` `2>` 与 0–2 描述符的 dup/closure（B2 起） | Shell 层 3 及以上 FD 重定向；标准 C exec 机制仍保留 0–31 |
| 命令替换 | `$()` 与 backticks，原始 stdout 上限 **1 MiB** | 无限长度输出 |
| here-document | 引用/展开/`<<-`、大正文 | — |
| 脚本兼容 | 无 shebang，或 `#!/bin/sh`、`#!/bin/dash`、`#!/usr/bin/dash` 且无额外解释器参数 | 其他 shebang 明确失败；不建 `/bin/sh` 文件别名 |
| 内建/函数/子 Shell | 支持 | — |
| 作业与信号 | 取消 = 前台 **Escape** | 后台 `&`、`trap`、`jobs`、`wait`、`kill` 等作业内建明确拒绝；无异步 POSIX 信号、无 Ctrl-C/Ctrl-Z 作业控制 |
| 参数/启动预算 | argc/env 各 64；spawn 单串 255 字节、exec 单串 4095 字节、startup 总 16 KiB | 超限明确失败与清理，不承诺任意长度 |
| 资源 | 不足时明确报错并回收 | 不承诺满盘/断电/扇区撕裂安全 |
| 其他 | `set -e`、`case`、点脚本、参数展开、临时环境变量、`exec` 真实替换（Make 后端/`exec` 内建） | 完整 POSIX/GNU Make、SMP、增量/并行 Make |

流水线退出码（C1 资格）：末段状态为准；缺失命令 127，其他 spawn 失败 126，
Escape 取消 137。

C3 报告的 `not_run_or_unsupported` 明确列出：完整 POSIX 与 GNU Make、SMP/Qt、
异步信号与后台作业、线程 profile fork/exec、任意 RPC 重放、掉电孤儿恢复、
新 SDK xypm profile 登记、无关随机长压测。后续路线见
[dash 计划](../../plans/dash.md)；**不要把未验收项写成已支持。**

## 常见问题

| 现象 | 原因与处理 |
|---|---|
| `xsh: ... not found`（`dash`） | 盘上无 `/usr/bin/dash`；用 `make run`（install ISO 首启安装）或 `scripts/install_dash.py --disk <disk>` |
| 脚本没反应/被当普通文件 | 必须 `dash /path/script.sh`；`exec-file` 不解释脚本 |
| 脚本里 GCC 报 `EPERM` | 用了 `exec-driver dash ...`（深度 1）；从 xsh 用裸命令 `dash script.sh`（深度 2） |
| 后台任务/`trap`/`jobs` 报错 | 属 C3 明确拒绝项，不是用法问题 |
| 中文路径/重定向失败 | 旧 dash + 旧 ASCII SDK 的已知失败；换组合 SDK 重建的 dash（回执见 [0069](../../work_log/0069_daily_utilities.md)），以实际资格报告为准 |
| 维护入口失败 | dash 运行时无法满足 `maint-run` 条件；先 `exit` 回 `xsh>` |

## 相关

- [getting_started](getting_started.md)、[in_guest_build](in_guest_build.md)、
  [xpk_packages](xpk_packages.md)
- 命令：[exec-driver](../supervisor/exec-driver.md)、[edit](../supervisor/edit.md)、
  [sync](../supervisor/sync.md)、[maintenance](../supervisor/maintenance.md)
- 范围与证据：[Shell 实现](../../implementation/shell.md)、
  [C3 资格报告](../../reports/dash_c3_20261026/qualification.json)、
  [dash 路线](../../plans/dash.md)、[xsh](../../xsh.md)
- 索引：[命令使用手册](../index.md)

## 相关工具：xos-diag（可选）

`xos-diag` 是独立诊断程序（构建产物 `user_xos_diag.image.elf`），**默认不装入发行工作盘**。
需要时从源码构建产物安装到客体 `/usr/bin/xos-diag`，再在 dash 中
`(exec xos-diag /path/to/program)` 启动并诊断直接子进程（见
`docs/implementation/fb12_fault_bundle.md`）。裸调用 `xos-diag` 而未安装会得到
`not found`（127），属预期。
