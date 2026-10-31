# 0114 — SSG P3B 双 Provider 聚合与隔离

2026-10-31，独立分支叠在尚未合并的 Browser Draft PR #10（基线
`687b6b1fa2fa1600162843ab4b259511e817701f`）上；Notes 的 text-range、保护、
revision 与可 join watchdog 只按需从 PR #9 的 `13c4521`、`dd11218`、`c9ff0bc`
移植，未合并或改写两条旧分支。目标程序由干净源码
`59291311956c82baa2afc22a18dab308abfa87f8` 构建；可移植回归入口由 `98d7716`
加入，后续 `a0449bd` 仅加强宿主默认拒绝检查器；`8d29888` 补齐回归入口对
SDK/Qt 变量的要求，均没有改变目标程序。

可信用户态 supervisor 创建 Browser 和 Notes 各自的请求/响应 Pipe，启动独立进程并
承担聚合 Consumer；来源授权来自实际预接线和 owner 许可。两个文本范围默认
拒绝，分别由 `--browser-text`、`--notes-text` 明确授予。新增
`src/user/apps/ssg_multi_session.cpp`、`src/user/ssg/multi_source.hpp`、
`browser_adapter.hpp` 与 `aggregate_diff.hpp`，复用 Browser 分页和 Notes UTF-16
revision 事务；契约在 [P3B 双源契约](../contracts/ssg_p3b_dual_source.md)。
范围为只读、有界、两来源，不含生产 Broker、任意发现、AI 执行器或全局权限系统；
没有更改内核、公共 ABI、QPA、驱动、时钟、IRQ 或调度器。

实际 QEMU 中三个独立 PID 与两组 IPC 的 baseline 经宿主独立重建；Browser 为 34 页、
267 节点，Notes 为 4,114 UTF-16 单位，分别与测试专用 liteHTML Oracle 和固定合成文本、
owner 摘要核对。节点身份按 slot/instance/epoch/local ID 分域。真实 Notes 编辑和真实
Browser 滚动各在另一 Provider 存活时测试；独立撤权、保护、跨 Pipe 拒绝、故障、退出、
取消和重启案例见[完整报告](../reports/ssg_p3b_dual_provider_20261031/README.md)。
`globalAtomicSnapshot=NOT_IMPLEMENTED`；各来源是顺序历史观察，完成项的采集后新鲜度
未验证。显示服务只有一个独占 Surface，测试中另一真实进程为无输入隐藏会话，未验证
双可见窗口或后台输入。

最终 stress：同一次客体启动内 48/48 完整会话通过，资源回到活动显示基线。
Browser、Notes 和 P1 的受影响客体回归在边界项定向重跑后通过。
52 个 Browser 结构验证器宿主测试及 9 个公开路径扫描器宿主测试通过；这些不替代客体
验证。完整参数化构建、回归入口、工具版本、输入与 ELF SHA-256、每组原始/导出哈希和
客体证据在报告及各证据包内。测试系统镜像为只读复用，未冒充本分支重建。

保留首次第二可见 Surface 被拒、编辑未保存退出超时、隐藏 owner 摘要时序失败等真实
失败及后续措施。旧单源 Consumer 偶发退出问题根因仍 `UNRESOLVED`；压力不复现不能
证明根治。静态审查发现旧两次采样路径末尾缺少 Browser 存活复查后，旧压力测试人为在
10/48 通过处中断；修正后另用新构建验证跨读取退出并重新开始压力测试。原始中断摘要的
`RUNNING` 字段按事实保留，另有操作员中断记录。又发现初版权限范围默认授予
而非分别显式选择，后一轮旧构建压力在 19/48 通过后主动中断并记录 PARTIAL；
收紧默认授权后以新构建重验，这两轮旧结果均不计入最终压力结果。

Notes 13 项边界回归首次因运行入口未要求 `XOS_BUILD_DIR` 在启动客体前失败；
补齐 SDK/Qt 路径后，使用原门槛在新目录重跑，13/13 通过且资源恢复。首次失败
与重跑证据分开保留。

复用 SDK 的完整许可材料核对未通过：线程 SDK 回执缺少 licenses 字段；旧系统 SDK
与当前源码组件清单分别有 24/32 项。独立源码侧检查通过 175 项登记材料核对及当时
43 个源码文件 SPDX 存在性；后续仅对 45 个变更源码文件重查 SPDX 标记。
这不等于 SDK 精确副本或归档逐成员的许可审查，不赋予
发行资格。后续需使用与当前组件清单一致的 SDK 重做完整材料及逐成员审查。

下一步：评审该 Draft PR 及其尚未合并的堆叠依赖；解决或持续调查旧退出超时根因；
在有多窗口/焦点能力的系统上另做真实双可见应用测试。不得将该限定实验推广为全局
原子快照、桌面权限系统、物理硬件资格或生产 Broker。Issue #37 历史对象可能仍有旧路径
残留，本分支不强推、改写历史或擅自关闭该问题。
