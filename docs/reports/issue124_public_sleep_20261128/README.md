# Issue #124：公开 sleep 与受限定时器的组合资格

包含 [PR #438](https://github.com/Xiao-John/XylophoneOS/pull/438) 时钟修复的全新静态
glibc SDK 已运行默认定时器矩阵，测试同步调用公开 `nanosleep`，没有启用
`--native-sleep`。xsh 与同一候选 SDK 构建的 dash 各运行五个程序，**10/10 通过**；
每次进程结束后资源均回到 `129693 / 3 / 1`。

本轮补齐此前 [原生等待阶段记录](../issue124_timers_20261128/README.md) 中尚待
验证的公开 sleep 组合路径，并完成 #124 对当前静态 glibc 的受限裁决。
`SIGEV_NONE` 不创建线程；`SIGEV_THREAD` 使用进程级至多一个调度线程和一个通知
线程。信号通知、CPU 时间定时器仍返回 `ENOTSUP`，不宣告完整 POSIX timers 支持。

## 实际结果

| 程序 | xsh | dash | 本轮实际覆盖 |
|---|---|---|---|
| 自身 CPU clock | 通过 | 通过 | 自身 PID/零 PID、错误输出保持、CPU 时间增长与分辨率 |
| `SIGEV_NONE` | 通过 | 通过 | 32 槽、耗尽恢复、代际失效、周期相位、参数/溢出、相对及绝对墙钟、fork 子对象清空 |
| `SIGEV_THREAD` | 通过 | 通过 | 调度线程创建失败回滚、重设唤醒、自删、单通知线程、`pthread_exit`/TSD 清理、删除复用、配额重试、属性及栈复制 |
| 既有 pthread 回归 | 通过 | 通过 | TLS、errno、once、锁、条件变量、信号量、barrier、TSD、join/exit、配额和双时钟等待 |
| 既有 detached 回归 | 通过 | 通过 | 每次 16 轮创建/detach/TSD、线程槽与内核栈恢复 |

两个 Shell 都实际观察到回调积压与配额耗尽后的 overrun 为 6；等待 TSD 析构和
原生线程回收后才发出下一次回调。构造阶段先占满四线程配额，THREAD 创建返回
`EAGAIN` 且输出不变，NONE 对象仍可创建；回收应用线程后 THREAD 创建恢复。
上述行为的完整标记和十次输出保存在 `qualification.json`。

## 来源与字节绑定

内核没有因本轮定时器资格发生修改，来自 main `344655c3`。对候选 SDK 的全部
378 项输入逐项比较：377 项与定时器实现快照 `06698bd5` 相同，唯一新增输入是
`clock_nanosleep.c`，其字节与 PR #438 的 `b63efb98` 完全一致。自身 CPU clock
wrapper 原已包含在定时器快照中，也与该 PR 相同。运行前后均校验系统源码、
系统产物、全部 1099 项 SDK 产物、五个测试 ELF 及 dash 的摘要。

| 身份 | SHA-256 或 build id |
|---|---|
| 系统 build id | `7e9d4063fa8154b7` |
| 系统 ISO | `bf08952e7d6126cc1b2ce060142258ffffd3e60e4ad4788b1a7ced22cf98f989` |
| 组合 SDK manifest | `53b2f5c7f71a48e8b8c3ef946b3a2ddf558390bda7b591ed4ddd9a157388ae55` |
| 组合 `libc.a` | `b29ce2da52299aa2c1880ce01fcbb4282d782c9f8140d1c98d5ec77401cd722d` |
| 原始客体报告 | `4bac7c09951b84d161f81b03a7cc51acf9a3e306dbeb9b22da6f792b3c942e47` |
| 原始串口记录 | `3ff36b1b868a09640fd7b72e46edd56f512c45cd7bb5f1fa68b60469cb96c81c` |

`qualification.json` 从实际 SDK 清单及客体报告派生，补充源输入比对结果、程序、
Shell 和工具绑定。首次缺声明的构建失败、首次公开 sleep 返回 `ENOSYS` 的失败，以及
原生等待阶段的成功均保留在各自原始记录中；没有修改旧报告，也没有将本轮结果
归给先前的 SDK。此前生产核心的普通/ASan/UBSan 检查见原生等待阶段报告；
公开时钟的独立 22 项普通/UBSan 与 4 次客体检查见
[df317843](../../work_log/df317843_issue124_glibc_clock_apis.md)。这些检查不是本轮重复执行。

## 重现

在发布的 glibc host SDK 开发环境中，令 `XOS_GLIBC_ARCHIVE` 指向固定并验签的
glibc 2.44 归档，`XOS_SYSTEM_BUILD` 与 `XOS_BASELINE_SOURCE` 指向上述 main
系统构建和对应源码。所有输出目录必须新建。

```sh
python3 scripts/build_glibc_sdk.py --archive "$XOS_GLIBC_ARCHIVE" \
  --output build/issue124-public-sdk --jobs 4
python3 tests/glibc_timers_guest.py \
  --system-build "$XOS_SYSTEM_BUILD" --system-source "$XOS_BASELINE_SOURCE" \
  --sdk-build build/issue124-public-sdk --output build/issue124-public-guest
```

本轮使用 GCC 16.2、Binutils 2.47.20260726、Python 3.14.10 和 QEMU 11.1.3。
QMP 关闭，通过串口运行；测试用的是 runner 默认 `all` 矩阵和公开 sleep。

## 完成范围

完成的是 [定时器契约](../../contracts/posix_timers.md) 与 #124 已裁定的静态 glibc
子集。共享 libc、冻结 newlib 的新增定时器、物理校时、长时间随机压力、信号通知
和 CPU 时间定时器不借用本轮资格。以最后应用线程的 `pthread_exit` 结束进程时，
应用应先删除线程通知定时器；内部调度线程是真实活线程。#125 的新内核交互验证
另行记录，本报告绑定上述未修改的基线内核。已发布 SDK 归档保持原字节，本轮是
新候选 SDK 的资格，并非 release 资产已发布的声明。

## 补充：与 #125 最终新内核的交互回归

在 #125 的最终系统 `ebaea6ff03805bad` 上复用上述已资格通过的 clock+timer SDK，
以默认公开 sleep 运行 `--suite timers`：NONE、THREAD、既有 pthread 和 16 轮
detached 四个程序各经 xsh/dash 执行，**8/8 通过**，每次资源回到该内核基线
`129692 / 3 / 1`。两个 Shell 的回调积压及配额重试 overrun 仍均为 6，
调度线程构造失败回滚、`pthread_exit`/TSD 后再通知及删除复用继续通过。

这一轮的 SDK、profile、dash ELF、四个测试 ELF 和源文件与前述基线运行逐项
比较，全部相同；更换的是系统镜像。新系统的 2254 项源码与 312 项产物，以及
SDK 全部产物在运行前后通过 runner 核验。系统 manifest SHA-256 为
`776a6ed96d5d9e54c0b9a90f93df6dcab92ad627f33d7304544c4dab5754f548`，ISO 为
`fd74929bb27140cbafba6654d3c7e825e245c1507474918acbb02b93c4a0eae2`。

`cross_kernel.json` 是这八次实际运行的独立派生记录，含原始报告、串口和源码
身份。原始报告 SHA-256 为
`f44f60862e2089fcf5d97f0f1dc9cb6646012f3dd5f5cb62ce6b4e8e9e5b2efd`；串口为
`49b82ff28c6a1ff1eaf5cfa6dea53b421b0813656cb87704c2a03dd11f259127`。
原十次运行的 `qualification.json`、native 阶段和独立 clock 报告保持原字节。

这是**原 clock+timer SDK 与 #125 新内核**的兼容性和生命周期交互资格。该 SDK
未包含 #125 的新版 libc join/目标线程 CPU clock wrapper，本轮没有把它称作
包含全部 libc 变更的统一 SDK，也未重复运行 `self_cpuclock`。令
`XOS_ISSUE125_SYSTEM_BUILD` 与 `XOS_ISSUE125_SOURCE` 指向上述固定新系统及其源码，
可用同一候选 SDK 重现：

```sh
python3 tests/glibc_timers_guest.py --suite timers \
  --system-build "$XOS_ISSUE125_SYSTEM_BUILD" --system-source "$XOS_ISSUE125_SOURCE" \
  --sdk-build build/issue124-public-sdk --output build/issue124-newkernel-guest
```
