# Issue #124：静态 glibc 定时器实测

当前 `SIGEV_NONE` 与有界 `SIGEV_THREAD` 的实现通过真实 SDK 构建和 QEMU 双 Shell
矩阵；每个入口运行 5 个程序，共 10 次通过并恢复资源。该轮夹具显式使用已有
原生 `sys47` 进行测试同步，**不代表公开 `nanosleep` 已可用**。首次默认路径确实
在 `nanosleep` 返回 `ENOSYS` 后失败；其修复和默认路径组合复跑独立跟进。

`qualification.json` 是从实际 SDK、宿主及客体报告选出的派生记录，保留原件摘要、
输入身份、实际标记和失败历史。目录采用平铺 `manifest.json`，未改动任何冻结报告。
内核来自 `main` 的 `344655c3`；glibc SDK 来自本分支的实现输入，并含独立的
自身 CPU 时钟 wrapper 提交 `37a8e825`，两类源码身份分别记录。

## 通过的行为

- 普通 POSIX 头声明、32 槽容量及耗尽恢复、删除后旧代际拒绝、周期相位、旧值别名、
  非法时长/溢出/标志拒绝、墙钟相对/绝对计时、fork 子对象清空与父对象保留。
- 重设及时唤醒调度器、回调删除自身、默认 256 KiB 与显式 64 KiB 栈、属性复制、
  删除并复用对象时已提交回调安全完成。
- 回调中 `pthread_exit`，TSD 析构尚未结束时不启动第二个通知线程；原生回收后继续。
- 一个正在执行的回调积压通知，以及四线程配额用尽后保留并重试通知；两个 Shell
  中这两种实际 overrun 均为 6，回调无并发扩张，原生线程/内核栈回到基线。
- 现有公共 pthread 用例与 16 轮 detached 线程/TSD/资源回归，和自身 CPU 时钟 sanity。
- 同一生产定时器核心的普通及 ASan/UBSan 宿主测试，精确检查可控时钟跳变、
  overrun 7/4、`INT_MAX` 饱和、资源不足、原生 reap 窗口和 fork 代际。宿主的替代层
  只提供受控时钟/线程原语，不实现另一份定时器。LeakSanitizer 未运行。

完整接口与仍不支持的信号通知、CPU 定时器、共享 libc 和冻结 newlib 范围见
[定时器契约](../../contracts/posix_timers.md)。

## 重现

在发布的 glibc host SDK 开发环境中，设置 `XOS_GLIBC_ARCHIVE` 为固定上游归档，
`XOS_SYSTEM_BUILD` 和 `XOS_BASELINE_SOURCE` 为对应源码的系统构建及源码目录。
所有输出目录必须新建；普通镜像和 glibc SDK 使用分别记录的身份。

```sh
python3 scripts/build_glibc_sdk.py --archive "$XOS_GLIBC_ARCHIVE" \
  --output build/issue124-sdk --jobs 4
python3 tests/glibc_timers_host.py
python3 tests/glibc_self_cpuclock_host.py
python3 tests/glibc_timers_guest.py \
  --system-build "$XOS_SYSTEM_BUILD" --system-source "$XOS_BASELINE_SOURCE" \
  --sdk-build build/issue124-sdk --output build/issue124-guest-native --native-sleep
```

移除 `--native-sleep` 即使用公开 `nanosleep` 的完整默认验证；上述 SDK 的该路径已知
失败，须先纳入独立时钟修复后重新构建和运行，不能以本轮原生同步结果替代。

## 调度线程创建失败补测

`scheduler_quota.json` 补充构造阶段的配额路径：先占满三个应用工作线程，
`timer_create(SIGEV_THREAD)` 返回 `EAGAIN` 且输出句柄不变，`SIGEV_NONE` 此时仍
可创建；回收工作线程后线程通知定时器正常创建。新夹具在两个 Shell 再次通过
8 次定时器及原线程回归，资源均恢复；生产 SDK 字节未变，公开 sleep 仍不由此资格覆盖。
