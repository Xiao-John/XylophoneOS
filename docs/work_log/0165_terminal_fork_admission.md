# 试行终端 fork 子会话登记

按 0164 的事务与资源边界，应用通过原终端会话发送 `fork_attach`；接收线程在发布
请求前用内核来源核验并登记子端点，确保新集合在应答前可见。最多三个会话共享模式，
派生项关闭可唤醒阻塞设备操作并被移除；回复失败按回复端点定位，避免误关闭其他
派生项。客户端提供 `register_fork`，失败或应答结果未知时调用者负责 abort 子进程。
普通 libc 尚未使用此接口。详细边界见终端控制契约。

宿主模拟通过来源核验、重复登记、错误句柄及客户端请求编码检查；这不是内核或
设备验收。提交 `b5d8603db607f909249b8bd46f00bf43a28dc241` 后，专用 supervisor
授予探针应用有限创建权限，在客体中通过子进程登记、提交、独立终端写入和退出，
以及原有输入、取消、应用退出和设备重授权检查。build ID `6a9b60dee1383478`，
系统 manifest SHA-256 `9a9ba0cd7590d009bb0a701a0840c4bb5949bd3f9ceb09e8325d6ee416baa2c0`，
镜像 SHA-256 `bcb76593a22feacd75db8e65743d5584c4269e33dce8d3220b78eeede0ba8702`，
串口 SHA-256 `9f36b92a8108d56c3593ade60e47e6618105a5744fcf7d20b93b46416d308526`；
报告位于 `build/w1_admission_b5d8603/`。

同提交的正常 Xsh build `f23cc544a1a04e6c` 上，终端 exec 模式、别名、CLOEXEC 和
失败 exec 探针 `passed_subset`；系统 manifest SHA-256
`289de6bbad3b4ea526c718f04b387f3386766cf428f0c7ec4779d4f6829caa3a`，SDK 树 SHA-256
`d705b15ab5885e07e8c3e02fc2560628542fe5330afe9ca2c4d752b99bcd7e97`，串口 SHA-256
`ce3bad0c1082f7adb1cf327ba45f13588ccc2279e94a1a8e61ebf6441062076a`；报告位于
`build/w1_admission_exec_b5d8603/`。普通 libc 的 fork 尚未接入；并发、取消、竞争、
异常及压力覆盖仍需补齐，不能将上述结果作为完整 W1/W2 资格。
