# 1c7f9abb · 下一阶段最新常规组合复验

从主线 `1c7f9abb` 的全新独立目录重建普通系统 `8530ecb637372dac`。源码包含
JavaScriptCore 静态 shell、固定 Test262 子集、Pumpkin FAT 导入和持久多账户、
D1 依赖映射后端及私有 DNS 诊断。编译使用锁定的 x86-64 工具和 lwIP 归档，客体
使用项目锁定的 QEMU 11.1.2。

`make -o build smoke` 实际通过 79 项常规客体检查、10 项许可材料核对，独立
ABI 表检查也通过。系统、SDK、QEMU 和原始日志摘要见
[验收清单](../reports/next_stage_1c7f9abb_20261126/manifest.json)。

普通镜像覆盖启动、内核、任务、进程、文件、持久状态、满盘、libc、存储和运行时。
私有 DNS、Pumpkin 管理配置、独立 glibc SDK 和浏览器引擎各有专项客体证据。
