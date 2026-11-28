# 普通静态程序的标准流兼容准入

本契约修正完整 FD 启动快照接入后，普通 raw native ELF 被无条件要求
`.xos.exec` v3 的兼容回归。没有新增 syscall、公共结构字段或 ABI 版本。

加载器先完成现有静态 ELF 检查。有效 `.xos.exec` v3 目标继续接收完整 v3
快照；标记不存在时，只有下列条件全部满足，普通 spawn 才使用既有 v2
标准流路由：

- 不是替换当前映像，也不是动态装载器的 pinned bootstrap 入口。
- 快照只有唯一的 fd 0、1、2；缺席的标准 FD 必须在路由中明确关闭。
- 每项只表示现有内核标准流，或者方向正确的阻塞管道；fd 0 为只读，
  fd 1/2 为只写。保留字段必须为零，不携带其他状态标志。
- 每项与实际 `stdio` 路由完全一致；同一对象的别名必须对应同一种类和
  同一底层句柄，重复底层句柄不能被声明成不同对象。
- 没有 Files 句柄、路径重定向、终端通道或任何无法由 v2 精确表示的内容。

额外 FD、Files 标准流、CLOEXEC 清理项、非阻塞标志、终端路由和真正的
exec 替换继续要求 v3 opt-in。加载器不能通过忽略快照项恢复兼容。
遇到存在但格式错误或版本错误的 `.xos.exec`，或者无法可靠检查的 section
table，明确返回 `ENOTSUP` 对应的原生 unsupported 错误和 inspect 阶段诊断；
不能把检查失败当成标记不存在。拒绝发生在创建目标进程之前。

动态 pinned 入口显式禁用本兼容分支，包括调用者未提供 prepare callback
的情况。动态 closure、READY 和能力授权协议不因此改变。子进程创建权仍由
原有 authority 策略决定；ELF 标记仅表示启动数据格式能力。

真实验收由 `scripts/build_static_stdio_probe.py` 和
`tests/static_stdio_compat_guest.py` 执行。它们使用指定 native SDK 的完整
快照，并显式编译当前生产 `load.cpp`，运行无 marker、有效 v3 marker 和错误
marker 的实际 ELF，验证管道数据、标准流别名、关闭的 stdin、全部拒绝边界，
以及由 supervisor 观察到的资源恢复。该组合资格不等于尚未构建的最终全系统
镜像资格；后者仍须重建并通过普通 installer 外部程序门。
