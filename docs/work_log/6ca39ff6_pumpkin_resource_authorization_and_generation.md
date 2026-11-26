# 6ca39ff6 · Pumpkin resource authorization and generation

2026-11-26 · 基于 `8f78f41a`，对照现有 files 对象身份、内核文件会话、通用端点和权限模型，补齐 [资源服务授权契约](../contracts/pumpkin_resource_service.md)。契约定义启动授予、一次性会话关联、服务拥有对象标签、操作授权点和注销或吊销时的在途次序。独立账户代际对照现有设备与显式开发环境的宿主记录，明确各自的保护范围和验收条件。

宿主夹具运行实际 `service_core` 与进程内适配器。适配器使用受信资源解析器查得的打开描述、对象权利和所有者标签，成功时才执行一次实际对象操作。测试覆盖同一对象的两个描述、活动会话和账户边界、两份权利、缺少标签、对象槽复用时的旧代际、注销、重登和吊销。最终读写计数确认拒绝请求未执行实际操作。

```sh
python3 tests/pumpkin_host.py --target-cxx x86_64-elf-g++
python3 tests/pumpkin_host.py --sanitize
python3 tests/abi_doc_consistency.py
```

普通和 ASan/UBSan 各通过 13 组，目标 freestanding 对象编译和 ABI 一致性检查通过。首次目标编译遇到宿主临时空间不足，改用 16 MiB 一次性内存盘后通过并释放。

实测范围为同循环授权及现有账户发布器回归。真实跨进程授权、受保护的持久对象标签、独立代际后端和生产硬件资格仍待实现及验收。
