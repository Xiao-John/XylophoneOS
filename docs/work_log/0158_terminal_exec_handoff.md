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

提交 `1361131` 后，正常 Xsh build `b06bc159557733d1` 的终端 exec 子集通过：
成功前后均 PID 10，未关闭别名与模式保留，CLOEXEC 别名关闭，缺失路径失败后
会话仍可用。ISO SHA-256 `19170eb8484c68bcaf7756b8c53031954286746b4b630a9b10201555398756bf`，
串口 SHA-256 `8f9107b8fdd3674fe4b5e250f589cdfdcdb9d4f6ca020c1b589d236dd2e7a494`，
证据位于 `build/w1_terminal_exec_run_1361131/`。专用终端交接 build
`52cc7038dab7fe29` 四组通过；内置 libc_hello 在独立盘上两次执行、输出和退出码
回归通过，串口 SHA-256 `bdce2c2b405ed5a5da534de60287e985654d403d23c9ef4b131a6b23f26d0700`。
最初 libc 检查没有附加盘，进入维护门控而未执行应用；该失败串口 SHA-256
`e6219df71fb92bdc93a6d1c253e78904baafee765410d007f14ee0692d703c20`。
现在增加全 CLOEXEC 和仅缺终端标记的目标拒绝探针，须提交后重新构建和验证。

提交 `dfedfc9` 后重建 build `2167a2ab6541b32f`，正常 Xsh 的两组 exec 客体检查
通过：同 PID、模式和未关闭别名保留，单个/全部 CLOEXEC 关闭；缺失路径和具有
`.xos.exec` 但无 `.xos.tty` 的目标均被拒绝，旧会话仍可用。ISO SHA-256
`5e0411445a4615686bcb15fe89bdc2a98e1f9545bf6d3651e63cc8dd3dc0e11d`，串口 SHA-256
`290fa421f87c62f03e9af6145d5b50af6145479d981f8cdbaf12fdf9bb400b2b`；回执和串口
位于 `build/w1_terminal_exec_run_dfedfc9/`。fork、线程、在途竞争和组合 SDK 重新构建
仍未完成；这些受限结果不代表完整 W1/W2 资格。
