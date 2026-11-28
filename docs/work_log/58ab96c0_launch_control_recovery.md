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
