# 3eba7c25 · 静态 JavaScriptCore 客体执行

使用锁定的 WPE WebKit 2.54.2、ICU4C 79.1、GNU glibc 应用 SDK 与 GCC 16.2.0，
完成真实 JSCOnly 目标的静态链接。`libJavaScriptCore.a` 有 194 个成员，
`jsc` 的装载段分别为 RX、R、RW，并有 TLS 段。
[构建输入和产物摘要](../reports/clarke_jsc_guest_20261126/build_binding.json)

首个链接目标在冻结 LLInt 表时中止。目标端把该表移入独占的匿名页，再在初始化
后冻结为只读。随后同一普通脚本走到了 shell 的退出 3 路径。原生启动栈只有
128 KiB，无法给默认 128 KiB 软件保留区及 JavaScript 执行同时留出空间。
XOS shell 在 1 MiB 的原生 pthread 栈上启动，保留 XOS 栈保护和 JavaScriptCore
原来的保留区。主线程等待，结束时由既有 glibc 进程路径回收。

生产和测试变更移植到 `e783fce2` 主线后，普通系统从 `4c56c325` 重建为
`578630c7c3b50563`。锁定 QEMU 11.1.2 的 xsh 从新工作盘运行原始脚本，
输出 `CLARKE_JSC_LLINT_PASS 6,15,36` 并退出 0。空闲页、任务和完成记录
在启动前后均为 `129696 / 3 / 1`。
[客体回执](../reports/clarke_jsc_guest_20261126/report.json) ·
[串口记录](../reports/clarke_jsc_guest_20261126/guest.serial.log.gz)

验收入口强制检查调用者提供的镜像资源基线。重跑使用同一 ISO 和静态 ELF，
按实际基线通过。将预期空闲页减少一页后，客体验收在脚本启动前拒绝该基线。
[基线不符回执](../reports/clarke_jsc_guest_20261126/baseline_mismatch.json)

该门验证静态解释器的普通脚本入口。ES262 通过率、WebCore 页面、跨进程渲染、
生产网络及长期浏览器运行仍有独立验收门。
