# aece9965 · 包恢复、Qt 材料和固定启动策略合入后的常规回归

从干净的主线 `aece9965` 重建普通系统镜像 `dacaf138dbabf003`。QEMU 11.1.2
通过 79 项常规客体检查，涵盖启动、进程、文件、持久化、满盘和运行时。10 项许可材料
与 ABI 表核对通过。源码、镜像、构建工具、lwIP 和 SDK 均绑定到本次回执。
[组合验收回执](../reports/next_stage_aece9965_20261127/manifest.json)

合入时沿用各模块实测配置。xypm 的 P2→P3 回执包含中断恢复、冷重启和重试，另验证
glibc 拒绝原 newlib 数据库且保持旧盘。Qt Quick 的搬移套件独立核对 42 个目标生成对象
和 823 个宿主归档成员。glibc 固定依赖闭包在专项镜像中复验正常启动与早期堆耗尽；
完整 GNU 动态解释器仍走独立资格。
[xypm](3ce98ac7_glibc_g4_xypm_p2_p3.md) · [Qt Quick](b7e8b6d7_qt_quick_generated_and_host_sources.md) · [固定启动策略](glibc_d1_fixed_startup_policy.md)
