# 0112 — SSG-P1 受限跨进程只读原型

2026-10-30。独立 `codex/ssg-cross-process-20261030` 工作树；从 Browser 可见性
修复 `45f7df2` 起步，保留原提交并合入 SDK Diff 修复分支 `8197004`。上游 main
初始核对为 `3377dbf35bdb43d850c9a2b8e8076da3be146f3d`；SDK #29、Fork #1/#3/#5
及管道探针 #30 在核对时均为 Draft/open。#5 依赖 #1，#3 独立基于 SDK；本分支
保留两条 SSG 依赖，不重写第二套场景树。通用管道探针及 runner 原样取自 #30 的
`91233bb72cc02dbc9cca805042def40712682dc2`，保留来源及其原 Apache-2.0 标识。

## 已实现和实际客体证据

受显式 spawn 委派的用户态 Session Parent 创建两条既有管道，分别预接到独立
Notes/Browser Provider 与命令行 Consumer。Consumer 的 Snapshot、详情、Diff、
角色/可见筛选及有限 watch 请求由 GUI 线程上的现有 `QtScene` / liteHTML
`SceneStream` 处理。帧协议有长度和序号，处理短读写、背压、EOF、坏帧、超限、
重放、超时和关闭；单连接一次一个请求。工作线程阻塞等待管道并投递 GUI 事件，
不在 GUI 线程忙轮询。provider 端定时器依赖 GUI 事件循环，非硬实时 deadline。

[最终客体验收](../reports/ssg_p1_cross_process_20261030/README.md)为
`PASSED_SCOPED`，17 项顶层检查：真实 Notes 父/提供者/消费者 PID 10/12/11，
真实 Browser PID 37/39/38；内核子进程事件及不同地址空间记录另存。客体键盘
把 Notes 文本从 `Visible note title` 改为 `aVisible note title`，独立消费者
读到节点、几何和版本 3→4 的实际 Diff；另观测 Notes 滚动、Browser 的实际链接、
正文、渲染片段及滚动。重载后旧 Browser 节点引用和真正重启后旧 Notes 提供者
引用均拒绝。序号重放、查询范围变化、截断结果、超大/半帧、两端超时、EOF、
受限权限和正常资源回收均有单独检查。完整帧、SHA-256、进程记录、QEMU 命令和
原始 guest 日志已冻结；串口只用于消费者/测试诊断，不参与 SSG 传输。

默认文本权限关闭；`--text` 是会话父进程显式选择。Qt 密码值继续屏蔽；可信
应用可对控件设置 `xosSsgProtected=true`，其子树在筛选查询中同样隐藏文本、
可访问/对象名和控件值。真实 Qt 测试控件验证该标记、密码及节点销毁，但不是
跨进程生产授权或自动敏感内容识别。Browser 本地探针在管道无文本权限时不能
扩大该权限，客体测试按前后两次 `DENIED` 验证。

单核/512 MiB、QEMU 11.1.2 TCG；系统 build `7ccd5871c0c00297`，镜像 SHA-256
`165686bb0de0b0b2f33645ede2cf10c2badb25ea363f3ef57ed74641503b0b08`。
SDK、Qt、工具、四个 ELF、源码和命令见冻结回执；系统镜像登记的 40 个内核源
及 5 个共享头与当前源码一致，SDK 重叠头 16 个一致，另一个只新增本次未用的
执行回执接口；另有一个本次未用的当前头不在 SDK 中。

当前工作树直接复用该镜像 manifest 做许可检查时，manifest 中的 Desktop 构建脚本
不在本堆叠分支，检查以缺文件失败；未把桌面源码复制进本分支来掩盖失败。针对
镜像来源工作树的原注册材料检查通过 7 项，当前分支本轮 13 个源码文件的 SPDX
另行核对；镜像来源工作树相对该旧 manifest 有两个测试源哈希不同。上述检查不是
完整 Qt 静态分发、逐成员或重链接许可审查。

#30 原管道探针重新运行，xsh 12/12、dash 未委派预期拒绝；旧 SSG Diff fixture
xsh/dash 各 12/12，旧 Notes 应用内回归 5/5。独立真实 Qt 安全 fixture 有 27 个
native 检查与 5 个 guest 检查。上述应用内测试是回归证据，不能冒充跨进程数据。

## 失败及尚未完成

第一次真实管道运行出现 `BAD_FRAME` 和 Qt 线程创建资源错误，原日志保留；Qt
诊断混入管道是可能原因，原始日志未保存坏帧头，故不声称根因已证明。随后把 Qt
诊断导向控制台、把额外 watchdog 线程改为 GUI 定时器。一次 harness 过早检查
未写完的状态行亦保留，不能当作通过。另一次 Browser 场景查询 `capped=true`，
Diff 正确返回 `RESET_REQUIRED`；消费者现以有限间隔重取完整基线，必要时重新
观察滚动，不把不完整结果标为完整。最终通过运行首次即得到完整基线，新增的
截断后重同步分支未在该通过运行中触发，恢复能力仍标为 NOT_RUN。

现有较大页面的旧 Browser 回归在本分支连续两次失败：早期 DOM/布局和真实链接
点击通过，但滚动 Diff 阶段查询被 30ms 遍历预算截断并返回 `RESET_REQUIRED`。
同镜像、同测试和已冻结旧 Browser 组合对照也以相同截断序列失败；原因未定位，
因此不能把旧完整 Browser 资格绑定本分支，也不能仅凭对照断言绝无新回归。
小页面真实跨进程 Browser 场景通过，并不保证更大文档的完整枚举；需要后续设计
受限分页或继续遍历并单独验收。

任意运行进程发现、逐消息内核认证、独立授权/远程撤销、多个消费者/订阅、生产
Broker、全局合成器遮挡、精确可见字形、所有未标记的敏感内容、跨进程动作、
动态 DOM/iframe/Shadow DOM、Canvas/WebGL 和媒体语义均未实现或未验。生产方向
及 C19–C29 下的通用机制审议见 [SSG-P1 契约](../contracts/ssg_p1_pipe.md)；不新增
SSG 专属 syscall，不复制 Linux 接口。LocalPilot 未来仅为普通消费者，本轮未修改
正式安装、代理配置或其它项目。无 `src/kernel/`、公共系统 ABI、QPA 或设备驱动
源码改动，不处理 PR #20 的驱动整改；未合并 main 或发布产品。
