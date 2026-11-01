# Xsh 显式终端前台入口

真实 Xsh 增加 `tty-run <program> [args]`：首次调用时启动 `/bin/terminal.elf`，
为 `.xos.tty` opt-in 程序在运行前附加应用会话并提供固定 xterm/80×24 环境，
等待应用后回收会话。后续可重复运行；启动后的旧 console 无法重新附着，因此在
终端会话活动时拒绝旧文件启动和内建镜像启动，不能声称旧 dash 或所有工具已接入。
默认仍是旧 shell 路径。附加/回收结果不确定时尝试受限服务恢复；恢复失败时无可靠
交互救援，不能宣称完整故障处理。fork/exec、多应用、前台取消和透明旧程序兼容仍缺。

`python3 scripts/build.py --output-dir build/w1_xsh_tty_v2_20261101` 通过，build ID
`a29ecd5546217c08`，仅提供安装 ISO，旧 real-mode 镜像不可用。探针新增 `--xsh`
模式，用正常 supervisor 和隔离盘启动宽字符、重入及 locale 应用；Python 编译和
差异空白检查通过。相关源码提交后才进行客体验证；本记录不宣称 Xsh 运行已通过。

提交 `c95a2b3` 的真实 Xsh 客体运行中，宽字符程序确实进入并返回提示符；原探针对
另外两个程序只检查无错误文本，证据不足以证明其成功退出。ISO SHA-256
`295f339492961b899b7d9536870c4f685f88e776ded1a8cb07739c976962c5a5`，串口 SHA-256
`20699601273ae3e84f1e51097d2c26fc9eac834471b8a87091d7677d1380efac`。现将探针改为
开启 Xsh trace，要求每个程序明确显示 exited/code=0，再提交后重测；默认演示任务在
首次交接前停止，避免干扰终端启动。

提交 `6fd7375` 的严格 trace 客体重测失败：宽字符程序完成屏幕交互后未回到提示符。
源码检查发现 supervisor 在应用独占期间输出 `[loader] started`，控制写被服务拒绝，
桥接因而进入 unavailable，随后无法正常 detach。失败 build `e6254583af2ea08b`，
串口 SHA-256 `a9cc7be28a89ae9f83e7a643061807269a306143776a5a4dd8b60d8fc48d759a`。
现禁止该阶段的 supervisor 输出；应用退出状态仍在 detach 后由 trace 输出，需提交后重测。
