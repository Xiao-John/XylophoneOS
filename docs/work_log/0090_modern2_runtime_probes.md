# 0090 Modern Platform Phase 2：运行时前置的实际分界

2026-10-29。独立分支`codex/modern2-runtime-probes`从新upstream `aaec2e9`开始，
旧工作区只读。仅新增客体夹具/runner、来源核验、设计报告及QuickJS构建输入，
没有内核/公共ABI/libc/Qt/驱动变更；LocalPilot只读固定main `9a21ebb`。

[报告](../reports/modern2_runtime_20261029/README.md)绑定build `8ac129a963b75031`、
真实重新编译QuickJS ELF、SDK/工具、512MiB专用测试盘与完整QEMU命令/串口。
14项测试器断言通过，包含跨模块/DOM/事件/Worker/WASM/origin的六个预期失败；
每次free=130279/tasks=2/completions=0。SharedArrayBuffer/Atomics仅名称存在，
无Worker或来源隔离成功声明。首轮未主动quiet demos的运行日志保留，后续只改测试器。

原始pypdf/CPython/LocalPilot调用链细分：filters无条件subprocess导入，
_posixsubprocess/select和flock/非阻塞就绪、进程组取消、安全文件身份为独立缺口。
公开依赖探针不含私有正文，实际执行保留原日志在本地；公有traceback需去掉私有源行。
可信文件owner/mode/路径/dirfd/防链接设计不给FAT合成值信用，不关闭原检查。
API1.0、认证身份、Operator与UNKNOWN仍须单独应用验收。

网络/VM/Pillow各自独立PR与worktree，本分支不合并它们；N2与PX4-A实现继续BLOCKED。
文档/ABI/许可材料及原始字节检查见报告validation；正式发行、完整浏览器/Code/Core
运行和安全产品资格NOT_RUN。复现命令、源码SHA及下一步责任均在报告，不需从聊天猜测。
