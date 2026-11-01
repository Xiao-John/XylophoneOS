# W1 交接与应用会话故障探针

干净提交 `3ad7707` 上，以 `--terminal-supervisor-probe` 重建 build
`35a1e86994d7aeba` 并运行 `tests/terminal_handoff_probe.py`，四组通过：串口
交接与 IRQ 输入、阻塞读取被控制请求中断、应用认证及退出、正常停止后重新授权。
ISO SHA-256 `b00f37fe46134202d2a787150712296e2ba755f191f307ef41c3e728d651770c`；
串口 SHA-256 `676054da73fe70926754764efd828ba6247de4f43798ce66c828d344e371cd5e`。
回执位于隔离工作区 `build/w1_handoff_3ad7707/terminal_handoff_report.json`。

新增独立应用：输出就绪后读取终端；supervisor 在有限延时后终止服务，要求应用读
返回错误、完成会话回收并重启服务。该定向探针的交叉链接与专用镜像构建已通过，
build ID `6e36101210fda308`；尚未客体运行，提交后再验证。延时不是读取已阻塞的
内核状态证明；输入输出丢失、在途请求精确结果及完整资源回收仍未建立资格。
