# Issue #124：自身 CPU 时钟与公开睡眠接口

本轮在已发布 glibc host SDK 开发环境中重新构建静态 glibc SDK，并以真实 QEMU
系统验证 `clock_getcpuclockid`、`clock_nanosleep` 和上游 `nanosleep`。xsh 与同一
候选 SDK 构建的 dash 各运行两个程序，**4/4 通过**；每次资源均回到
`129693 / 3 / 1`。系统源码是 main `344655c3`，没有为该验证修改内核。

`qualification.json` 是实际构建、宿主测试及客体原始报告的最小派生记录，记录
候选 SDK、源文件、ELF、工具和原始串口记录的摘要，以及实际运行标记。
本目录使用平铺清单，不重写旧报告，也不将构建成功等同于运行资格。

## 行为与验证

- `clock_getcpuclockid(0)` 和自身 PID 返回自身进程 CPU clock；其他 PID 明确
  返回 `ENOSYS`。查询错误使用直接返回的错误码，并保持 `errno` 和输出不变。
- 真实 CPU 时间和分辨率仍来自既有 sys89 v1，未以墙钟替代。客体执行计算负载后
  CPU 时间增加，分辨率为正。
- 相对 `CLOCK_REALTIME` 与 `CLOCK_MONOTONIC` 睡眠使用单调经过时长；绝对
  realtime 在唤醒后重新检查墙钟截止点，覆盖两次采样之间的抢占窗口。
- 上游 `nanosleep` 调用新的 XOS `clock_nanosleep`，并按 glibc 原实现将正错误码
  转为 `-1/errno`。真实客体验证了相对/绝对等待、过期截止点、参数和溢出错误、
  `errno`/remainder 保持，以及睡眠期间另一 pthread 能继续执行并被回收。
- 自身 CPU clock 的 10 项宿主检查通过；睡眠实现的 22 项宿主检查分别以普通和
  UBSan 模式通过，包含绝对 realtime 转换溢出、采样偏移后的二次等待和原生失败。

## 重现

在 glibc host SDK 环境中，令 `XOS_GLIBC_ARCHIVE` 指向固定上游源码归档，
`XOS_SYSTEM_BUILD` 与 `XOS_BASELINE_SOURCE` 指向对应的 main 系统构建和源码。
所有输出目录必须是新目录。

```sh
python3 scripts/build_glibc_sdk.py --archive "$XOS_GLIBC_ARCHIVE" \
  --output build/clock-api-sdk --jobs 4
python3 tests/glibc_self_cpuclock_host.py
python3 tests/glibc_clock_sleep_host.py
python3 tests/glibc_self_cpuclock_guest.py \
  --system-build "$XOS_SYSTEM_BUILD" --system-source "$XOS_BASELINE_SOURCE" \
  --sdk-build build/clock-api-sdk --output build/clock-api-guest
```

## 范围

本轮完成 #124 的自身 CPU clock 与公开 elapsed sleep 基础；定时器对象和线程通知
属于独立的 P1 变更。本报告不代替该组合验证，不关闭整个 Issue。目标线程 CPU
clock 由 #125 处理。CPU 时间睡眠、跨进程 CPU clock、信号打断/异步取消、墙钟
设置、共享 libc 和冻结 newlib 均不借用本轮静态 glibc 的资格。既有发布 SDK
归档保持原字节；本轮结果属于新候选构建。
