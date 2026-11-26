# XOS 下一阶段开发计划

起点为整合提交 `9f7a9a0f`。开发基线和已通过的验收分别记录。
glibc C/C++ 已有 Linux arm64 实构建和静态客体证据，并发 C++ 普通运行曾异常退出，复跑通过仍不能关掉该问题。Qt 已有 Core、Gui/QPA 和 Widgets 资格。现有浏览器已实测本地页面和受控 HTTP，正式引擎、HTTPS 及生产 DNS 仍须各自验收。

## 依赖与交付顺序

| 任务与负责线 | 依赖 | 交付与验收 |
| --- | --- | --- |
| 旧阻塞及证据复核 · 运行库 | 首先进行。核对当前源码、已知问题与已有修复，保留原始成功和失败 | 独立确认 SDK 实际构建和候选资格。对确证缺陷提交最小修复、回归和资源检查。普通 C++ 需要双入口重复验证，正负路径分别记录。诊断链接模式另行登记。 |
| glibc 迁移 · 运行库 | C/C++ 资格和包管理 profile 是默认切换依赖 | 保持两套工具链和 sysroot 隔离。按实际依赖迁移 dash、C/C++ 探针、系统工具、xypm、Qt 与现有重要应用。每批记录构建、双入口、负向、资源及升级/卸载。切换前演练从 glibc 恢复到冻结的 newlib 独立 SDK，验证旧包及数据可用。退役指停止默认构建和新增依赖，归档回退所需源码、工具、配方和回执。动态链接按 D0 至 D4 独立验收。 |
| QML/Qt Quick · Qt | 勘查、源码锁及构建图可立即开展。正式资格绑定合格 glibc、Qt、QPA 与显示服务 | 分离宿主生成工具和目标模块，固定 Qt 版本、依赖、许可及补丁。先验证 QML 引擎与静态模块加载，再用 Quick 软件渲染跑场景、文本、输入、帧推进、窗口重开和资源回收。为外部应用提供可复用 SDK、构建示范及运行诊断。 |
| Mobius、ClarkE · 产品 | 产品命名可以先落地，入口和包 ID 迁移需核对包锁、工作盘和安装器 | 统一可见产品名和正式入口，保留经验证的旧入口或迁移路径，验证旧镜像、包升级、卸载与数据定位。保留冻结证据中的旧名。逐一核查 Aurora 的产品、共享框架、协议及历史含义，协议编号和 SDK 名称按契约演进。 |
| Pumpkin · 身份服务 | 从现行权限模型及 IPC 契约设计，按需对接文件服务和 Mobius；核心服务可与 GUI 独立开发 | 用户态身份、认证和会话服务。定义创建、认证、注销、吊销、资源归属和持久化恢复。权限取内核认证主体的对象权利与用户态策略的交集。POSIX UID/GID 只作兼容投影，UID 0 不赋予额外内核权利。持久化路径先明确身份库一致性、授权迁移和 FAT 能力边界。验收覆盖正确与错误认证、会话失效、重启恢复、跨用户拒绝和资源回收。 |
| ClarkE 浏览器升级 · 浏览器 | 产品迁移可独立。引擎资格依赖 SDK、显示/渲染、网络、证书、时间与熵 | 更新 WebKit M0 实作比较与实测依赖清单。允许调整端口路线，以可构建、可维护、许可和隔离证据裁决。先保留现有本地和受控 HTTP 对照，再验证脚本、DOM/渲染、受控 HTTPS、用户态网络服务及独立渲染进程。覆盖失败、取消、资源上限与进程退出。 |
| 持续审计与最终整合 · 总协调 | 每次接口变更与每批交付；最终以实际组合树为准 | 防御性源码审查覆盖并发、性能、资源、权限、ABI、架构边界与证据。逐项复核 reviewer，记录事实和适用范围。独立 worktree、构建目录与模块分支/PR。组合镜像为空输出重建，绑定源码、SDK、镜像、配置、工具和回执。 |

## 接口与验收规则

- 公共 ABI、SDK 默认配置、`docs/state.md` 及组合验证由总协调统一处理。各负责线先在独立 worktree 工作，分别记录提交和验收。
- 核心只负责隔离、受保护的 IPC 和对象权利及生命周期。身份库、认证、会话、显示及网络业务策略留用户态。涉及权限或接口语义时同步契约、ABI 登记与旧版兼容方案。
- 按 C27 分别记录 xsh 和 dash 的客体证据。把编译、验证通过、失败、未运行和不适用逐项登记，分别保留源、二进制、镜像、工具和运行条件。
- 并行启动顺序为运行库旧阻塞复核、Qt 依赖勘查、Pumpkin 服务设计。总协调推进产品标识与兼容面，Qt 勘查结束后独立展开 ClarkE 引擎选型与构建。各条线最终在同一主线验收。
- 只有每条线的交付和组合验收均有证据，本阶段才收口。默认切换、回退演练、存量迁移和 newlib 退役各有独立验收记录。

## 2026-11-26 里程碑

| 任务 | 现有证据 | 下个验收门 |
| --- | --- | --- |
| glibc 迁移 | 分配器修复后，静态 C/C++ SDK 在 xsh 和 dash 各通过 15 项普通运行。隔离的 glibc dash 预览在两个启动入口各通过七项。 | 路径及启动接口的独立评审，继而验收实际外部程序、管道、here-document 与默认切换回退。 [分配器](../work_log/54ff4de4_glibc_allocator_locking.md) · [dash](../work_log/aff51323_dash_glibc_preview.md) |
| QML/Qt Quick | 静态 glibc QtCore 与 QtQml 已合入。目标 QtQml 在独立客体执行 JS、绑定重算及三轮引擎回收，同一版本通过 VM 配额失败验证。 | glibc QtGui 和宿主 `qsb` 已构建。继续验证目标 Quick 软件渲染和显示/输入闭环。 [QtCore](../work_log/8d6f3d2c_qt_e18_glibc_qtcore_target_build.md) · [QtQml](../work_log/d8bd3467_qt_e18_target_qml_and_vm.md) |
| Mobius/ClarkE | 各自打包后通过两次安装、ClarkE 升级、各在 xsh 和 dash 客体启动、两次卸载及原用户文件回读。ELF 回执核对完整 SDK 树。 | glibc Qt 产品迁移、正式发行材料与旧工作盘迁移组合验证。 [产品包复验](../work_log/af27a498_desktop_product_packages.md) |
| Pumpkin | 原生服务、私有槽和独占授权客户端已合入。测试配置下的真实持久守护进程通过双 Shell 认证、吊销及重启读回。 | 复核持久守护进程，接入独立代际来源、生产凭据发放和资源服务。 [IPC 复验](../work_log/cbf3d657_pumpkin_daemon_review_fixes.md) · [持久守护进程 PR #195](https://github.com/Xiao-John/XylophoneOS/pull/195) |
| ClarkE 引擎 | 静态 ICU 已在目标实测标准化、大小写、分词和排序。WebKit JSCOnly 配置实际选中三个目标 ICU 归档。 | 继续 JSCOnly 编译、链接与客体执行，再推进 WebCore 和原生网络。 [ICU PR #194](https://github.com/Xiao-John/XylophoneOS/pull/194) |

首个主线快照已完成内核、存储、运行时、包流程和易失身份会话的组合复验。
[组合证据](../work_log/d1c062ce_next_stage_combination.md)

## 专项依据

[开发纪律](../Discipline.md) · [宪法](../xos_plan.md) · [ABI](../contracts/abi_registry.md) · [glibc](glibc_port_scout.md) · [动态链接 D0](../contracts/dynamic_linking_d0.md) · [SDK profile](../contracts/xypm_sdk_profiles.md) · [Qt](qt.md) · [Qt 平台](../contracts/qt_platform.md) · [权限模型](permission_model_glibc.md) · [网络](network_development.md) · [浏览器](webengine_port.md)

## 组合复验补记

进程修复合入后的 `db8e15dd` 已在锁定 QEMU 上通过完整常规 smoke。
glibc 日用工具、独立 Qt Quick 应用、Mobius 会话、Pumpkin 盘外代际和 ClarkE
目标布局按各自门禁继续推进。
[整合检查点](../work_log/8a09e2c7_next_stage_glibc_checkpoint.md)

组合候选 `d155a61f` 从干净源码通过 79 项常规及 50 次 glibc 客体运行，
独立核对了两种 dash 入口。此后合入了 Mobius glibc 软件包生命周期、xypm
原生 glibc 维护、Pumpkin 开发代际回退防护和 ClarkE 目标线程布局。完整 C3、
动态链接 D1–D4、Pumpkin 生产认证与资源服务、ClarkE 完整引擎和最终主线镜像
继续按各自门禁验收。[绑定复验](../work_log/ea2d71c6_next_stage_combined_guest.md)

`77b48ecc` 主线快照重新通过 79 项常规 smoke、10 项许可材料和 ABI 检查。
独立的 `39b4e51a` 主线快照以同源签名静态 SDK 重跑了两种 Shell、进程、
文件和管道的 50 项检查。音频顺序修复使原生 glibc 安装镜像在冷启动中完成
真实 P2 安装、恢复清理及 26 文件核对。后续 SDK 切换与退役按最终候选验收。
[安装验收](../work_log/03c0fe80_install_bundle_before_audio.md) ·
[运行库和 W1 组合回执](../work_log/77b48ecc_runtime_acceptance_checkpoint.md)

主线 `8b40d62f` 已纳入独立 glibc C/C++ 应用 SDK。干净 Linux 容器用它构建并打包
两种语言的应用，客体检查了安装和冻结 newlib 回退。下一轮需在正式应用冷启动配置下
验收首个 dash 子进程，并用最终系统与 SDK 复跑存量应用、包事务和旧盘回退。
[SDK 记录](../work_log/245042e2_glibc_sdk_selection.md)

同一主线含 GNU glibc PIC 归档、Pumpkin 开发配置跨重启登录、ClarkE 的目标 JSC
配置保护和 LLInt 地址适配。D1 接下来要把已验证的私有入口栈接到真实解释器，
并贯通高地址映射与早期文件会话。Pumpkin 需要独立资源服务和部署端受信边界，
ClarkE 完整引擎需要在客体执行后再参与浏览器组合验收。
[PIC 归档](../work_log/8e477872_glibc_shared_io_and_pic_archive.md) ·
[Pumpkin 登录](../work_log/317b1813_pumpkin_operator_login_across_reboots.md) ·
[JSC 配置](../work_log/b73f1f0f_clarke_jsc_config_protection.md)

主线已合入 ClarkE 受控 HTTPS 安装包、Pumpkin 持久登录与独立 broker、D1
原生解释器入口准备。来自含前两项的主线快照的普通镜像，在同一工作盘上启动了
两个已安装产品和独立 Qt Quick 应用。SDK 发布预览已复验旧版原件的回退路径。
余下的共同门包括正式安装配置的首个 dash 子程序、迁移的软件组合和真实动态
解释器。浏览器仍需完成 JavaScriptCore 执行、WebCore 和生产网络。
[同盘组合](../work_log/dcbbd42a_desktop_products_combined_guest.md) ·
[D1 入口 PR #260](https://github.com/Xiao-John/XylophoneOS/pull/260) ·
[发布预览 PR #263](https://github.com/Xiao-John/XylophoneOS/pull/263)

主线 `1c7f9abb` 含 JavaScriptCore 静态 shell 和 16 次 Test262 子集执行，
Pumpkin FAT 导入和多账户验收补齐，D1 映射器和私有 DNS 诊断已合入。普通镜像
重建后通过 79 项客体检查、10 项许可材料和 ABI 表。当前继续推进 D1 真正的
运行时重定位、受信部署的 Pumpkin 代际与凭据、ClarkE 的 WebCore 与网络组合，
并保持 SDK 切换与回退的独立验证。
[普通镜像复验](../work_log/1c7f9abb_next_stage_mainline_replay.md)


`9ed4428d` 已含 Pumpkin 持久登录的 Mobius 会话、ClarkE 真实 HTML 分词和 Skia 软件栅格。
前者验证两帧桌面、注销、持久吊销与旧登录回归，在线管理员撤销和部署凭据仍待验收。
后者验证确定像素、FAT 输入绑定和资源回收，完整 DOM、CSS 布局及 Qt 视口仍待组合。
[Mobius 会话](../work_log/242820a4_pumpkin_mobius_session.md) ·
[Skia 栅格](../work_log/4cc10377_clarke_skia_raster.md)

显式 glibc stock 候选 `7f88e4f9070640c2` 已验首个 dash 子进程、空盘自动安装和 13 个
日用工具的重启与卸载。同盘外部应用组合在两次启动中运行 C、C++、GNU Make 和日用
工具。首轮真实 dash 因预览版拒绝命令替换而退出，首次失败保留。组合复测确认文件
持久化与回读，默认切换仍需命令替换、存量应用、升级及冻结 newlib 回退的独立证据。
[安装 PR #288](https://github.com/Xiao-John/XylophoneOS/pull/288) ·
[应用组合 PR #289](https://github.com/Xiao-John/XylophoneOS/pull/289)
