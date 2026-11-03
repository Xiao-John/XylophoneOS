# 0124：用户态终端控制与启动交接基础

2026-10-30。继续 W1：sys82 增加仅当前 COM1 PIO 持有者可查询的内核认证授权者
PID；失权后拒绝。用户态终端服务通过该身份筛选两条由授权者建立、对端也是授权者的
sys81 通道，线程分别等待 IRQ 和控制请求；读取、写入、错误计数与停止使用有界消息。
驱动状态由等待字互斥保护，关闭 IRQ 后回收接收线程。控制客户端和加载器的启动前
回调先建立通道、最后授予 PIO，失败由调用方清理通道；设备授权后的失败仍须隔离。
契约见 `contracts/pio_grant.md`，回调说明见 `e04_loader_sdk.md`。

`python3 scripts/build.py --output-dir build/w1_terminal_handoff_v2_20261030` 通过，
使用 x86_64-elf-g++ 16.2.0，构建 ID `f77c7ff864fc8630`；生成的独立
`user_terminal.image.elf` SHA-256 为
`716ef683d40dae510b97ef61191db551c2bd8075dce7ca9226f8dde799c233e5`。
服务、驱动、控制客户端均已交叉编译链接，控制客户端链接进 supervisor；终端 ELF
只是独立构建产物，尚未安装或启动。所有这些是构建证据，不是客体验收。
`python3 tests/docs_consistency.py`、`python3 tests/abi_doc_consistency.py` 和
`git diff --check` 通过；构建快照早于本记录的文档更新。

服务只接受 supervisor 控制请求，读写非阻塞；没有普通应用会话、前台输入权、
termios、逐键模式、原有 shell 的接管、阻塞读、恢复或救援。工作线程报错不会主动
唤醒等待控制请求的主线程。PIO/IRQ 交接、缓存和错误、调度竞争及控制协议均未在
客体运行验证；授权成功后即使启动失败也会隔离 COM1。所有相关更改提交后才能运行
客体验收，不能将本组构建或旧证据当成 W1/W2 通过。

下一步先设计并实现 supervisor 实际控制/故障路径和服务与应用会话，解决恢复及旧
console/ESC 的一致性；补齐设备状态与等待的真实闭环，再接入 termios、宽字符
ncurses 和编辑器。建立覆盖启动失败、权限、并发和设备故障的客体测试并在提交后运行。
