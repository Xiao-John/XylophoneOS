# 单终端 select 的直接客体检查

2026-11-03。现有 ncurses 测试间接调用受限 `select`，无法单独确认参数拒绝和不消费
输入的契约。现将定向断言加入真实终端交接应用：空输入的立即查询应超时并清空读集；
无效 timeval、多个读取描述符、写集合和不存在的描述符分别按当前契约返回错误。
宿主随后发送一个字节，应用先等待可读、再立即查询一次仍可读，最后读取原字节，
从而验证就绪检查未消费数据。专用 supervisor 的客体 runner 要求新标记。

此项只覆盖单个终端描述符、确定的空/就绪和参数组合，不扩展到通用 select、所有
竞态或其他对象。提交后从匹配源码重建专用系统、应用及 SDK，再在真实 QEMU 客体
执行；若失败先追查真实实现和 fixture，不以编译通过代替结果。

提交 `ee37e2676efa707374f49fc2723bc9577f1db49d` 后重建专用系统，build ID
`218b0f8a7d91249f`，`tests/terminal_handoff_probe.py` 的 14 组检查通过，包含新增
`single_terminal_select_timeout_errors_and_nonconsuming_ready`，以及既有 PIO、IRQ、
交接和 fork 子集。系统镜像 SHA-256
`296a8733dcb3089891db18dac43693f65e02dac3bca63ec6f5445fdc90a7ea2b`，SDK 树 SHA-256
`39664d200b3e7bc7b305eb18e65d8ce2dba0f0611af139116b59245eaa4dcde7`，串口 SHA-256
`f928fa391f5ad4fc0a14a812adb3420df51b37f99e59777e2dd1ed5f6169c680`；报告在
`build/w1_select_system_ee37e26/`。这些检查不证明完整 W1/W2 或通用 select。
