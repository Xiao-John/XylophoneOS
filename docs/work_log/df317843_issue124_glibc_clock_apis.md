# Issue 124 glibc own-process CPU clocks and elapsed sleeps

2026-11-28；基线 `344655c3`。关联
[#124](https://github.com/Xiao-John/XylophoneOS/issues/124) 的 P2 裁决，作为定时器
P1 的独立基础 PR。此前 newlib 的部分时钟能力不能证明当前默认 glibc 接口可用。

## 修复

增加 `clock_getcpuclockid` 的 XOS 实现：零 PID 和自身 PID 映射到既有自身进程
CPU clock，先核验 CPU clock 可用性；其他 PID 返回 `ENOSYS`。保持直接错误码、
调用者 `errno` 和失败时输出不变。时间与分辨率继续使用未改变的 sys89 v1。

真实定时器和线程客体测试还复现 glibc `nanosleep` 返回 `ENOSYS`。固定 glibc
2.44 的上游 `nanosleep.c` 已正确转发 `__clock_nanosleep`；缺口是后者仍选用
通用未实现桩。因此只新增 XOS `clock_nanosleep.c`，通过已有 sys47 完成单调
截止点等待。相对 realtime 使用单调经过时长；绝对 realtime 先取单调时间、
再取墙钟，唤醒后复查以防采样抢占导致提前返回。乘法、加法和有符号原生时域
均检查溢出，CPU 时间睡眠返回 `ENOTSUP`，不虚构信号中断或 remainder。

两个实现均未增加 syscall、未改变 sys89 或线程 ABI，也未宣告完整 POSIX timers。
`docs/e06_libc.md` 同时澄清当前默认 glibc 与历史 newlib 记录的关系。

## 实际验证

所有构建与运行均在已发布 glibc host SDK 的开发环境执行，使用 GCC 16.2、
Binutils 2.47.20260726、Python 3.14.10 与 QEMU 11.1.3。

- 固定并验签的 glibc 2.44 完整 SDK 构建成功，核验 1096 项产物。
- 自身 CPU clock 宿主检查 10 项通过；实际睡眠生产代码普通和 UBSan 各 22 项
  通过，包含 realtime 转换溢出、采样偏移、原生失败及错误输出保持。
- 新 SDK 的两个程序经 xsh 和同 SDK dash 运行，4/4 通过，CPU 负载确实增加
  自身 CPU 时间，公开 `nanosleep`、绝对两种时钟与线程等待均正常。
- 每次客体进程结束后资源回到 `129693 / 3 / 1`；系统 build id
  `7e9d4063fa8154b7`，系统源自未改动的 main `344655c3`。
- SDK 输入、所有 SDK 与系统产物、程序和 shell 字节在运行前后均再次核验。

纯自身 CPU wrapper 的先行 SDK 构建保留为中间产物，没有将其称作含公开 sleep
修复的 SDK。以上资格全部绑定后续同时含两个实现的实际候选 SDK。
[平铺公开记录](../reports/issue124_clock_20261128/README.md) 给出身份、实际标记、
测试范围和复现命令。独立审阅核对了上游转发逻辑，并重跑宿主检查。

## 后续关系

本 PR 仅引用 #124，定时器 P1 应在纳入该基础的组合 SDK 上用默认公开 sleep
重新运行后闭环。目标线程 CPU clock 属于 #125；不把自身 clock 当作目标线程
实现。共享 libc、冻结 newlib、信号和异步取消均未获得本轮新增资格。
