# glibc D1 固定闭包的 GNU 启动策略

固定闭包启动以 XOS 的私有入口契约为准，使用立即绑定，拒绝解释器直接调用及主程序的搜索路径和审计标签。GNU 系统预加载文件、通用 loader 环境处理和依赖的 cwd 路径计算退出该配置。解释器诊断共用继承的原生输出句柄，使早期错误输出独立于共享 libc 的描述符表。其他 glibc 配置沿用上游行为。

## 主线组合验收

从主线 `fcebc61b749d95405711d25bba3649010c0c09f6` 复验实现提交 `97eb4875c766acbd0faec63f30c2da719139659b`。重新验签 glibc 2.44，构建 C SDK、GNU rtld 探针和系统镜像 `7490da2f6a9ad6ae`。探针识别出 GNU 入口，确认固定闭包对象移除了通用搜索、预加载和 cwd 调用，缓冲区诊断经实际原生陷入输出。正式 `ld.so` 目标仍由 `dl-sysdep.c` 拒绝。启动入口资格仍是 D1 固定闭包的现有范围。

在 QEMU 运行已认证双 DSO 的早期堆耗尽和普通启动，返回 127 和 0，资源分别恢复到 `129696/3/1`。夹具在触发堆耗尽前已关闭 pins，随后的普通轮确认可以重新以写模式打开依赖。完整 GNU 启动、共享 libc 和外部应用入口将在对应共享启动组合上验证。[构建绑定](../reports/glibc_d1_fixed_startup_post301_20261127/binding.json) · [客体结果](../reports/glibc_d1_fixed_startup_post301_20261127/guest.json) · [原始串口](../reports/glibc_d1_fixed_startup_post301_20261127/guest.serial.log.gz)

复验使用 `scripts/build.py`、`scripts/build_glibc_sdk.py`、`scripts/probe_glibc_rtld.py --closure-tls-fixture` 和 `tests/glibc_d1_closure_tls_guest.py`。客体报告包含镜像、SDK/profile、GNU rtld 对象、原始串口与所用命令的完整绑定。
