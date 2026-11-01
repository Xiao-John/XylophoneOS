# 单线程终端 exec 交接

在显式通道保留机制上接入单线程 libc：仅在至少一个终端描述符未设 CLOEXEC 时
保留对应两个通道，并在 startup v3 的固定扩展中传递发送 token 和下一消息序号；
replacement 验证内核认证通道并恢复描述符别名。目标必须同时声明 `.xos.exec` v3
和 `.xos.tty` v1；失败 exec 不改变旧会话，所有终端描述符均 CLOEXEC 时默认关闭
通道。fork 和线程 profile 仍明确不支持。该实现假设单线程客户端无在途请求，不
对异常对端承诺透明恢复。

宿主客户端模拟验证 v3 序号恢复；首次常规系统构建因 libc_hello 镜像超过 128 KiB
失败。将该 SDK 对象分 section 并仅对内置 libc_hello 链接时启用 section GC 后，
常规 build `c7a9a261e8b4ffb5` 通过；其他应用链接策略保持原样，须进行目标回归。
新增真实 Xsh 终端 exec 探针，覆盖成功同 PID、保留别名、CLOEXEC、模式与失败 exec；
已交叉编译，客体必须在提交后运行。尚不授予 W1/W2 完整资格。
