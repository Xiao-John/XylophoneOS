# 终端底层权限客体探针

`tests/w1_wait_smoke.py` 改用安装 ISO，适配当前系统超过旧 real-mode 容量的构建；
增加 PIO/IRQ 非授权请求检查，以及未授权 COM1 `inb` 应触发 #GP 的独立模式。
通道探针继续验证受控端点、配额、短缓冲和退出后的旧句柄；pipe 只验证真实 pipe
截止与关闭。原 runner 的 console IRQ 等待断言来自已撤回的内核 UART 路线，现不再
执行或宣称通过，console 等待仍列未运行。

本组先准备入口，提交后在匹配系统/SDK及独立测试盘运行；授权后边界、fork/exec、
撤权竞争和完整 W1 仍不由这些负向探针证明。
