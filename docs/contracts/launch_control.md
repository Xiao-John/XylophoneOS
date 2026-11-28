# 启动控制与公共等待 v1

本契约登记 `xos/launch_control_abi.h`、`xos/launch_control.hpp` 和
`src/user/sdk/launch_control.cpp`。复用 sys81 单槽通道、sys4/5 消息、sys20 完成
记录及既有 exec channel preserve，不新增 syscall 或改变旧 startup。

## 身份、权限与编码

父在 owned building child 提交前调用 record_child，创建容量 128 字节的两个
单向通道：ready 是 child 到 controller，ack 方向相反。局部分配失败关闭已
创建通道且不改调用者输出。内核四个 sys81 通道的 owner 限额继续生效；registry
的 16 槽不是同时控制 16 个 child 的承诺。

子每次交换通过内核枚举核对真实 PID、peer/controller PID、handle 和方向；
用户自报 PID/handle 不授予身份。sys63 提供非零 64 位 nonce，排除当前及最近
发出的值，最多四次；熵失败不回退到时钟/PID/常量。lifecycle generation 每次
授权递增，取消也不复用；它不同于 artifact ID。

artifact 的 ID/SHA-256 必须一起非零或全部为零。父 admission callback 在
登记、PREPARE、READY 三处核对当前批准策略；没有 callback 仅允许全零 artifact。
callback 必须有界、不可重入，context 生存期覆盖登记。实际 ELF、同一 readonly
OFD、只读 capsule 和可信 bootstrap 由加载器验证；自报摘要不能替代执行字节。

magic `0x314c525443534f58`，version 1，原生 x86-64 整数编码。

| 结构 | 字节 | 字段 |
| --- | ---: | --- |
| descriptor | 80 | magic，version/size，controller/child PID，generation/nonce/deadline，ready/ack handle，两个 reserved u64 |
| artifact | 40 | ID u64，SHA-256 32 字节 |
| message | 128 | magic，version/size/type/phase，generation/nonce/PID/deadline，status i64，artifact，三个 reserved u64 |

artifact 在 message 偏移 64，reserved 在 104。未知版本、错误 size、reserved
非零、额外字节、错误身份/方向/serial/nonce/root 均拒绝。type 是 PREPARE=1、
ALLOW=2、READY=3、READY_ACK=4、FAILURE=5、FAILURE_ACK=6、CANCEL=7、CANCEL_ACK=8。
phase 是 NONE=0、PREPARE=1、MAP=2、RELOCATE=3、INITIALIZE=4、ENTRY=5、COMMIT=6。
FAILURE 要求负 status 和合法非零 phase。

## 初始启动与后继 exec

初代为 pending generation 1。父 await_ready 泵全部登记 child；子 notify_ready
发 READY 并等待精确 READY_ACK。父收到消息后重查时间及 admission，发送批准
ACK 后将 pending 提升为 active。READY 拒绝返回 ENTRY phase 负状态，子不得
进入 main。ACK 入队不能替代子实际消费；子也在接收 ACK 后检查期限。

旧映像使用 active 身份发 PREPARE，附目标 artifact 和新绝对 deadline。父校验
后生成新 serial/nonce，由 ALLOW 返回候选身份。拒绝返回旧 serial/nonce、相同
请求 deadline/artifact、PREPARE phase 和负状态。子须已消费 ALLOW、两个队列
为空，才把两个 handle 放入 exec preserve 清单并执行真正的同 PID exec；
内核仍独立拒绝有在途消息的 preserve。

提交前失败用 pending 发 CANCEL，收到 CANCEL_ACK 后保留旧 active。提交后
不能返回旧地址空间；新 bootstrap 发 READY 或 FAILURE 并等待 ACK，失败时
真实非零退出。父不以协议错误伪造 sys20 completion。FAILURE/CANCEL 不要求
重新 admission，因此撤销后仍可清理。

用户态 grant 与 kernel exec commit 之间没有原子即时撤销。单 controller
以 grant 为本次入场批准点，READY 前再次复核。READY 拒绝阻止进入 main，不能
撤回已发生的构造/IFUNC 副作用；持久策略与跨后代当前撤销另行验收。

## 期限、恢复及并发

每次交换共用非零有限绝对单调 deadline，申请时最多距现在 60 秒。零或
UINT64_MAX 无效，已过期返回 thread_error_timeout（-13）。收消息、admission、
随机调用后重取时间。旧 active 的初始 deadline 可已过期，但新 PREPARE 必须
使用有效新期限。没有用 yield 次数估计时间。

初始 pending 超时关闭通道；后继 pending 超时保留旧 active，不擅自杀旧映像。
精确匹配最近过期候选的迟到消息只消费、不 ACK。旧 ALLOW/CANCEL_ACK 已排队
而子一直停顿到期限后时，新 PREPARE 可消费同一认证 controller、同 child、
格式正确且已过期的旧答复，然后等待本次精确答复；不接受旧授权、不重发请求。
真正已提交 exec 的超时不会恢复旧映像，新的 bootstrap 必须结束并产生真实完成。

SDK wait/wait_any、newlib waitpid、glibc __xos_wait_child 经可选弱 hook 泵全部
登记 child，再以 sys20 nonblocking 取真实完成。无活动控制通道时保留直接
sys20。直接绕开 SDK 使用阻塞 sys20 不会自动泵协议。WNOHANG 不睡眠；阻塞
等待用 channel wait_many 与最多 10 ms 刻度，更近的授权期限提前唤醒。
await_ready 提前观察的完成暂存后只交付一次；诊断保留到有界 registry 槽复用。

短临界区使用 PID 原子 try-lock，竞争返回 busy，不跨阻塞等待持锁。fork 私有
副本发现 PID 变化后清空继承 registry，也可接管来自不同 PID 的复制锁，但不
关闭父通道。同 PID 线程不能通过该路径解除别人的锁。没有自动重启或未知结果重放。

## 兼容与资格

header、controller archive 与调用方须成套重建；旧静态程序无需链接本模块，
回退使用旧静态启动路径。没有新增 libc 私有结构或 syscall/errno 分配。
本次恢复先取得严格 target 编译，新 host/guest 结果见
[工作记录](../work_log/58ab96c0_launch_control_recovery.md)。上一轮已丢失工作区的
结果不作为本次源码资格；GNU 公共运行库组合由对应模块另行验收。
