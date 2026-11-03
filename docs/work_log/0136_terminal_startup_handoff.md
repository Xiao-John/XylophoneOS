# 0136：终端应用启动页交接基础

2026-10-30。新增试行 startup2 终端发送 handle：受信 supervisor 的 prepare 回调在
目标 building 时创建并附加应用通道，加载器随后把非零发送 handle 写入启动扩展并
映射启动页，最后启动进程。应用 `connect_startup` 用该 handle 枚举内核认证通道，
核对控制者、服务对端和方向；handle 本身不产生权限。仅显式 opt-in 的 `.xos.tty`
v1 只读 ELF 才允许此路径，缺少标记的旧程序被拒绝；原普通 spawn 不改变，exec/fork
及 libc stdio 接入仍未实现。编码和失败清理见 [SDK 契约](../e04_loader_sdk.md)、
[ABI 登记](../contracts/abi_registry.md)及[终端契约](../contracts/terminal_control.md)。

专用 supervisor 探针新增一个独立 opt-in 应用：在子进程运行前创建和附加通道，应用
读取启动扩展并经终端输出，退出后 supervisor 回收。测试盘准备脚本纳入应用 ELF，
源码和每件产物均由 manifest 校验。宿主模拟验证未知/正确启动 handle 的拒绝与连接；
命令见 0135。`python3 scripts/build.py --terminal-supervisor-probe --output-dir
build/w1_terminal_startup_20261030` 通过，build ID `6d9096955dc7e02b`；
应用 ELF SHA-256 `a4a512860e7e56182f00d7d561d822398806179c06aec20d5d7350381006dcb5`，
目标 `readelf`/`objdump` 确认 `.xos.tty` 为只读 ALLOC 16 字节标记。构建早于文档更新。

专用探针未运行客体；标记拒绝、启动失败时会话清理、通道关闭、用户隔离、资源和
并发尚无目标证据。宿主模拟不运行加载器或进程创建。下一步实现 libc stdio 与真实
终端模式，并处理成功/失败 exec、fork 和故障恢复；所有相关修改提交后再客体验收。
