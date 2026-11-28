# P0 启动控制恢复与重新验收

基线是恢复后的远端模块组合 `f7240faae1fe1ef6f3dfae44fa21aef864849f23`。
原执行环境丢失，未发表的启动控制和产物无法恢复为原字节。本工作按已记录
契约重新实现，不修改旧报告，不把上一轮 33 次 guest 结果绑定到新源码。

## 源码 checkpoint

恢复共享 C ABI、当前 admission callback、READY/ACK 与 PREPARE/ALLOW、提交前
CANCEL、提交后 FAILURE、有限绝对期限、过期排队答复恢复、公共 wait 泵以及
fork 复制持锁 registry 的 PID 边界。SDK 导出 .h/.hpp；两套 libc wait 入口与
普通/threading/glibc support 归档同步纳入接口。

首个 checkpoint 在核验的 Preview 2 launcher 内完成严格 freestanding C++
目标编译：GCC 16.2.0，Wall/Wextra/Werror/Wconversion/Wshadow。新实现的
host/sanitizer、真实 native guest、GNU 公共 runtime 组合在此 checkpoint
仍为 **not_run**。后续资格会补到本记录，不借用先前工作区的验证结果。

新接口及兼容范围见 [启动控制契约](../contracts/launch_control.md)。父批准身份，
执行字节的完整同 pin 验证由动态加载器负责。当前是有界单 controller 注册表，
未宣称进程树配额、跨后代即时撤销或持久代际恢复。

## 本次源码的重新验收

2026-11-28 在 Preview 2 中完成新的验收。生产 controller 自源码 checkpoint
`3d7747f1` 后未修改；测试和产物均重新构建，未复用丢失环境的通过结果。

| 范围 | 新结果 | 关键检查 |
| --- | --- | --- |
| 生产源码 host trap model | 15 个独立进程案例，普通和 ASan/UBSan 各一次，共 30 次通过 | 登记原子性、配额 4、认证方向/PID、畸形输入、期限、撤销、失败诊断、排队过期答复、背压、wait 泵与准确一次完成 |
| 实际 host fork | 普通与 sanitizer 均通过 | admission 持有 registry lock 时 fork，子 PID 接管私有复制锁，父状态不变；不是内核 fork 资格的替代 |
| 原生 guest | 11 类 × 3 轮，共 33 次通过 | READY、真实同 PID exec、提交前失败/CANCEL、提交后 FAILURE、两处 admission 拒绝、超时、早退、畸形消息、多 child、过期 ALLOW/CANCEL_ACK 恢复 |
| 每次 guest 资源检查 | 33 次均精确回到同一基线 | `free=129781, tasks=2, completions=0`，真实 completion 消费后 channel 清空 |

构建 ID `cd41a13a9b8bfc61`。fixture 以匹配 SDK 的 header、归档和 linker script
链接。runner 在 guest 前后核对系统 manifest 的所有源文件和产物、SDK tree、
fixture 输入和 ELF SHA-256。sys20 的真实状态是各 case 自己断言的依据，
未把协议拒绝改写成虚假的子进程完成。

首次新 guest 暴露 fixture 的时序错误：向仍在 building 状态的 child 发初始
descriptor 被内核正确拒绝。fixture 改为 spawn 返回后发送，再 await_ready。
失败报告与串口记录单独保留，最终 33 次来自重新构建的源码。

可审计的摘要、串口文本（记录原始及换行规范化 hash）、host 日志、source/artifact 绑定和复现命令在
[本次资格记录](../reports/launch_control_recovery_20261128/README.md)。该资格不
代替 GNU 共享运行库和 R2 closure/catalog 组合的独立验收。
