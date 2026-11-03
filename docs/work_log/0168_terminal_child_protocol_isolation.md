# 终端子会话的无效消息隔离

复核应用接收线程发现，子进程在已授权输入通道上发送短于固定协议消息的内容时，
原实现将整个接收线程退出，导致父会话和其他子会话一起关闭。现仅对收到非空短消息
的派生槽关闭其通道、移除槽并唤醒设备等待；根会话的协议错误仍结束整个前台会话。
关闭竞态先按失效端点重查，其他传输错误仍按原错误路径处理。

新增正常 Xsh 探针：fork 子进程直接向自身授权通道发送短消息，确认该子通道关闭，
父进程回收子进程后仍能查询终端模式并输出。提交
`c1c5dfd4f6e355b3f5b4c5f0716866f5b5b4fed5` 后重建并运行正常 Xsh 客体，结果
`passed_subset`，包含短消息隔离及既有 fork、超额回滚、读中断与 exec 回归。
build ID `5462f3bfbe605014`，系统 manifest SHA-256
`54b2333da752281eb4e333f5acb2d2251ec04a709976d295ac3a53a6a68426ac`，镜像 SHA-256
`802382cc4f6c02fbb3844111db8c51192f0f7cbb9c3b1fb2ea8c5827423c0a4b`，SDK 树 SHA-256
`fd0401fb4124fc22d1a5d0a163da0f2cd2f38b2a63c108c307d5123644893ec0`，串口 SHA-256
`da1e324a48e4e4a88094d93f1d859a9850b47a2702a18cfae138bdbf2f6b370a`；报告位于
`build/w1_bad_child_run_c1c5dfd/`。这不覆盖恶意消息的全部种类、并发交错或完整 W1/W2。

进一步让另一个已登记的子进程保持存活，等短消息子进程被撤销并回收后，验证该
兄弟进程仍能查询模式和输出，父进程随后仍能查询模式。提交
`27a57e5a6fb6307f1dda38425c8ef1279437efed` 后重建的正常 Xsh 客体结果
`passed_subset`，该兄弟隔离断言和既有 fork/exec 子集通过。build ID
`44f61f56659660fe`，系统 manifest SHA-256
`0db34b2cc5269215b05245737bf95caac9577153d2e5ae7aab3eda4313b9e8b7`，镜像 SHA-256
`78dafa56df4a800f200ce6e2913f9269221eed19d280a1f0defffdd8f9d57721`，SDK 树 SHA-256
`20087342ff21014cc6fd305c8f8dcec793d958c9f4f55478882e73043ac3be44`，串口 SHA-256
`0ae8d1b637d1e20d6da6711a733cbab8781b7f546699439cd54b4686219bf501`；报告位于
`build/w1_sibling_run_27a57e5/`。不外推至任意在途操作或所有交错。
