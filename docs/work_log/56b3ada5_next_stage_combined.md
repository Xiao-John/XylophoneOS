# 56b3ada5 · GNU 解释器合入后的普通客体回归

从干净的主线 `56b3ada5` 重建普通系统镜像 `4d533678d20f4da7`。QEMU 11.1.2
通过 79 项客体检查，覆盖启动、进程、文件、持久化、满盘和运行时。10 项许可材料
检查和 ABI 表核对通过。回执绑定源码树、系统镜像、普通 SDK、lwIP 和实际工具版本。
[普通组合回执](../reports/next_stage_56b3ada5_20261127/manifest.json)

该主线包含工作区应用 SDK 的可逆默认选择、Pumpkin 分 UID 代际提供者，以及固定依赖
闭包的 GNU 解释器。三个专项各保留自己的镜像和证据。GNU 共享 C++、发行 SDK 默认
切换和 Pumpkin 生产介质继续按各自的条件验收。
[工作区 SDK](50e9a5a4_glibc_sdk_default.md) · [Pumpkin 部署](f1d2a697_pumpkin_provider_deployment.md) · [GNU 解释器](glibc_d1_linked_interpreter.md)
