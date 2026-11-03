# 终端底层权限客体探针

`tests/w1_wait_smoke.py` 改用安装 ISO，适配当前系统超过旧 real-mode 容量的构建；
增加 PIO/IRQ 非授权请求检查，以及未授权 COM1 `inb` 应触发 #GP 的独立模式。
通道探针继续验证受控端点、配额、短缓冲和退出后的旧句柄；pipe 只验证真实 pipe
截止与关闭。原 runner 的 console IRQ 等待断言来自已撤回的内核 UART 路线，现不再
执行或宣称通过，console 等待仍列未运行。

本组先准备入口，提交后在匹配系统/SDK及独立测试盘运行；授权后边界、fork/exec、
撤权竞争和完整 W1 仍不由这些负向探针证明。

提交 `087dd8a` 后在干净快照重建 build `0e0a46422ef14893` 并分别运行 `--probe
pio`、`irq`、`channel`、`wait`，均为 passed_subset：非 supervisor PIO/IRQ 请求被
拒绝，未授权 COM1 inb 触发 #GP；通道受控收发、配额、短缓冲及对端退出后的旧句柄，
以及 pipe 超时、就绪与关闭检查通过。ISO SHA-256
`3bda3eb8d9fb636ac53b97101f689ad78b4f0b23e85b9fae46f02465c69cb4ba`。
各回执和串口位于隔离工作区 `build/w1_{pio,irq,channel,pipe}_087dd8a/`；串口
SHA-256 依次为 `de495aad6e9bd374905cc38d2568c9f84a49e592a7b1440c03d39ab33ccf77b3`、
`274876a227bd962ba074a27518557d9522be17e6f1d3f0c979f2f32d0977016c`、
`c379c8960f4fac680ee5f7772af7a79e91830447cac08fd451aaa39b2260e02c`、
`7f9d758a98640a19ef2077f8a825c6e992f4b5e590a72937d5e51d4e23a6ba54`。
未覆盖的授权边界和竞争仍按各回执 `not_run` 处理。
