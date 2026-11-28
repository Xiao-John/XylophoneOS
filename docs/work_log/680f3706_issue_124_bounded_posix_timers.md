# Issue 124 bounded POSIX timers

2026-11-28；基线 `344655c3`。关联 [#124](https://github.com/Xiao-John/XylophoneOS/issues/124)
及其已明确的 P1/P2 裁决。自身 CPU clock wrapper 先独立提交为 `37a8e825`，由主
agent 在独立分支完成纯 P2/时钟资格；本记录负责定时器主体。

## 实现

五个 `timer_*` 入口由 `ENOSYS` 桩改为进程内实现。`xos_timer.c` 维护有代际的
32 槽对象、独立时间域、一个可唤醒调度线程和至多一个 detached 通知线程。
回调参数复制、通知合并计数、配额不足后的有界重试、等待原生回收再发通知、
属性私有复制及 fork 子对象清空共同处理删除/重设/退出竞态。

实现不改变 syscall、sys89 v1 或线程 ABI，不把定时器对象送入内核。`SIGEV_NONE`
不创建线程；`SIGEV_THREAD` 沿用原生 pthread 和其栈/TLS 清理；信号及 CPU 时间
定时器明确拒绝，不发布完整 POSIX timers 能力位。共享 libc 与冻结 newlib 不借用
本次静态 glibc 的资格。具体错误、时域、合并和生命周期见
[契约](../contracts/posix_timers.md)。

`_Fork.c` 在单线程 fork 子分支、用户 atfork 回调前清空定时器；保留代际防止
继承句柄指向新对象。Makefile 只增加 rt 私有实现，原五个公开入口和调用约定保留。

## 实际验证与失败

使用已发布 glibc host SDK 中的 GCC 16.2、Binutils 2.47.20260726、Python 3.14.10
和 QEMU 11.1.3。完整 `build_glibc_sdk.py` 以锁定并验签的 glibc 2.44 源码构建，
1098 项产物经实际清单校验；生成的 `gnu/stubs.h` 不再将五个定时器入口标成桩。
普通及 ASan/UBSan 宿主测试均在同一 SDK 环境重新执行，LeakSanitizer 未运行。

第一次 SDK 构建因 `__libc_fatal` 缺少 `<stdio.h>` 声明失败，补充包含后从固定
源码重新完整构建。第一次默认客体运行中自身 CPU clock 通过，定时器池/代际
通过后 `nanosleep` 返回 `ENOSYS`（88）；这是原 glibc 迁移缺口，未伪报成功。
主 agent 负责其独立时钟修复；本分支添加可显式选用原生等待的测试模式，继续
验证定时器实现本身。

`tests/glibc_timers_guest.py --native-sleep` 在内核构建 `7e9d4063fa8154b7` 上
通过 10/10 次实际启动，分别从 xsh 和同一新 SDK 构建的 dash 运行：NONE 定时器、
THREAD 定时器、自身 CPU clock、现有 pthread、现有 16 轮 detached 回归。
每次资源回到 `129693/3/1`。客体额外观察到回调退出/TSD 清理窗口、四线程配额
耗尽后的恢复、两种通知积压均得到 overrun 6，并确认内部线程和内核栈回收。

[平铺公开证据](../reports/issue124_timers_20261128/README.md) 包含完整边界、
重现命令、实际 SDK/系统/ELF/工具身份、宿主输出、全部十次客体标记和历史失败摘要。
源码、SDK、镜像输入在运行前后重新校验。它是原始报告的最小派生版本，不是
对旧冻结报告的重写。

## 交接

定时器生产代码及真实行为已通过上述独立资格。公开 `nanosleep` 修复纳入组合
SDK 后须移除 `--native-sleep` 重新运行默认矩阵，再将 #124 的公开接口闭环状态
更新为完成。此记录不把原生测试同步冒充公开 sleep 可用。

非目标项：信号子系统、CPU 定时器、共享 libc 配置、冻结 newlib 新增定时器、
物理校时和长时间随机压力。普通 exit 回收进程；若仅靠最后应用线程的
`pthread_exit` 结束进程，应用应先删除自己的线程通知定时器，内部调度线程仍
是真实活线程。没有把这个生命周期限制隐藏为已完成的全 POSIX 语义。

## 补充：构造阶段的配额回滚

在相同 SDK 上增加并实际执行调度线程创建失败路径：三个应用工作线程占满
四个原生线程槽时，THREAD 定时器创建返回 EAGAIN、输出句柄保持不变，NONE
对象仍可用。释放并 join 工作线程后 THREAD 对象恢复创建，随后既有回调配额、
TSD 和线程回归继续通过。两个 Shell 的 8 次补充启动全部恢复资源；普通及
ASan/UBSan host 也重跑通过。派生结果见公开报告中的 `scheduler_quota.json`，
前一份 qualification 保留原 SDK/夹具结果，未冒称已测 public nanosleep。

## 补充：公开 sleep 组合资格完成

2026-11-28，纳入 [PR #438](https://github.com/Xiao-John/XylophoneOS/pull/438)
`b63efb98` 的公开 sleep 修复后，重新完整构建静态 SDK，再以默认
`tests/glibc_timers_guest.py` 运行，不传 `--native-sleep`。
自身 CPU clock、NONE、THREAD、既有 pthread 和 16 轮 detached 回归分别通过
xsh 与同一组合 SDK 构建的 dash，10/10 实际启动均成功，资源全部回到
`129693 / 3 / 1`。两个 Shell 的回调积压和配额重试 overrun 仍均为 6，
构造阶段 EAGAIN 回滚、TSD 清理及原生回收顺序继续通过。

组合 SDK manifest 为 `53b2f5c7f71a48e8b8c3ef946b3a2ddf558390bda7b591ed4ddd9a157388ae55`，
`libc.a` 为 `b29ce2da52299aa2c1880ce01fcbb4282d782c9f8140d1c98d5ec77401cd722d`。
378 项 SDK 输入逐项与定时器快照 `06698bd5` 比较，唯一新增的
`clock_nanosleep.c` 与 #438 精确相同。1099 项 SDK 产物和所有系统/ELF/Shell
身份在客体运行前后均核验，系统仍是 main `344655c3` 的
`7e9d4063fa8154b7`。本轮未包含 #125 的新内核，不借用其资格。

[独立最终报告](../reports/issue124_public_sleep_20261128/README.md) 记录十次结果、
实际标记、精确 SDK/源码绑定及原始报告/串口摘要；此前原生等待阶段与已发布的
时钟报告保持原字节。公开时钟自身的验证和范围见
[df317843](df317843_issue124_glibc_clock_apis.md)。本补充完成此前“交接”段所列
默认组合验证，PL-0004 更新为 `fixed`，仅指 #124 已裁定的静态 glibc 受限子集。
信号/CPU 定时器、共享 libc、冻结 newlib 等非目标项及上述调度线程生命周期
限制保持明确；本记录不宣告新 release 资产已经发布。

## 补充：#125 新内核交互回归

2026-11-28，复用前述相同 clock+timer SDK，在 #125 最终系统
`ebaea6ff03805bad` 上运行默认公开 sleep 的 `--suite timers`。四个程序各经
xsh/dash 执行，8/8 通过，每次资源回到新内核基线 `129692 / 3 / 1`；两种积压
overrun 仍均为 6，调度配额回滚、回调/TSD/原生回收顺序及既有线程回归通过。
profile、dash 和四个测试 ELF 的摘要均与原基线运行完全相同，SDK 也未重建或改写。

新系统 manifest 为 `776a6ed96d5d9e54c0b9a90f93df6dcab92ad627f33d7304544c4dab5754f548`，
ISO 为 `fd74929bb27140cbafba6654d3c7e825e245c1507474918acbb02b93c4a0eae2`，
2254 项系统源码、312 项系统产物及所有 SDK/ELF/Shell 字节在运行前后核验。
[cross_kernel.json](../reports/issue124_public_sleep_20261128/cross_kernel.json)
记录独立的八次实际结果及来源；原有 `qualification.json`、native 阶段和 clock
报告保持原字节。此资格只表示原 clock+timer SDK 与新内核的交互通过；该 SDK
没有纳入 #125 新 libc wrapper，不代表全部 libc 修复已经构成统一发布 SDK。
