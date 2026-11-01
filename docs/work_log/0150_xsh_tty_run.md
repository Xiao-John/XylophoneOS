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
