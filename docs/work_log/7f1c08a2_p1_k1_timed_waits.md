# P1-K1：libc 定时等待与显式中断

日期：2026-11-28。基线 `6332527ab64e92371266363f41f3247717a3cac8`。
ABI 预登记由独立 PR #444 完成；本次不增加 syscall，不修改冻结 SDK。

## 改动

基线已有 `nanosleep` / `clock_nanosleep` 的正常 elapsed-time 等待。本次把
等待后端接到现有私有 wait-word，为每次等待登记 PID、全宽原生 TID、非零
sequence 和单调 deadline，提供安装到 SDK 的 `xos/sleep.h`。v1 票据恰为
48 字节；两个 reserved 字段保持零。查询不解引用公开 `pthread_t`，不授予
跨进程权限，也不延长等待生命周期。

接受的中断先提交 wake word，再唤醒目标；原子比较/入队避免丢失唤醒。
旧票据不能命中新一轮等待。相对等待返回规范化剩余时间，绝对等待不改
remaining；成功和其他错误也保留输出。`clock_nanosleep` 保留 errno，
上游 `nanosleep` 负责错误转换。明确保留晚到的原生 wait 错误，不因此时
deadline 已经过期而误报成功。wake 失败不撤销已可见的中断。

四个活动槽与内核每进程四线程上限一致；满表返回 EAGAIN，序号不回绕。
正常/错误退出在锁内退休票据，静态单线程 fork 清空子表，成功 exec 采用
全新运行时。`pthread_cancel` 仍为 ENOTSUP，信号和其他阻塞 API 未接入该
扩展。完整公开契约见 [libc_timed_waits](../contracts/libc_timed_waits.md)。

## 实际验证

最终 system `7ea902f2bff60edf` 和 SDK 在源文件冻结后重建。SDK 使用已验签
的 glibc 2.44，目标工具链 GCC 16.2.0；dash 和三个 C 探针均从该套 SDK
生成。没有混用早期 sysroot 或注入替代的 libc 等待实现。

- xsh / dash 各执行核心中断、fork/exec 和既有 clock-sleep 探针，共 6 场
  真实客体运行全部通过。核心探针先观察原生 waiting 计数，再投递票据；
  覆盖四种时钟/相对绝对组合、旧请求撞上同 TID 后继等待、四个并发活动槽。
- 单线程 fork 的子进程拒绝父 PID 票据；失败 exec 后等待仍工作；成功
  same-PID exec 验证 PID 未变、票据表为空并正常完成等待。
- 每场均恢复 **129690 free pages / 3 tasks / 1 completion** 的实测基线。
- 生产 sleep-table 代码的 10 组确定性测试在普通运行和 ASan/UBSan 下通过；
  生产 clock-nanosleep 的 24 案例在普通运行和 UBSan 下通过。
- 系统全量 source/artifact、SDK 全量 input/artifact、实际执行 ELF 的哈希在
  运行前后及证据导出时再次验证。公开包包含源码、工具、产物身份和无损
  压缩的原始串口记录，flat manifest 只索引叶子文件。

初次 host sanitizer 运行因宿主 ptrace 环境使 LeakSanitizer 失败；原报告与
原始诊断保留。后续明确关闭 leak detection，ASan/UBSan 通过；不把 LSan
记为通过。第一次匹配 system/SDK 的 6 场 guest 也通过，但随后修复了晚到
原生错误的优先级，因而重新完整构建并执行最终 6 场。发展版本证据保留，
不冒充当前源码的验收。

公开证据：[P1-K1 报告](../reports/p1_k1_timed_waits_20261128/README.md)。
最终验收限于静态 glibc 的已记录 x86-64 QEMU 环境；共享 libc、物理硬件、
SMP、信号投递和 pthread 取消均未扩大声明。
