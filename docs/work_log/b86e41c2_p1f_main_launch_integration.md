# b86e41c2 P1-F 主线 native 启动清理整合

## 完成结果

F checkpoint6 `a3874f94616f6ffbed368d39d9e6bb21ebb9ee9d` 与主线
`93758f59488c32161cc15b909513a91106408cf1` 整合。共同基线为 `6332527ab64e92371266363f41f3247717a3cac8`，
新增验收证据之前的源码 tree 为 `8d107bf92105f46b9b3d5514cf92a36707361376`。
新 native 系统 `7117377f147d895c` 在真实 guest 运行原 runner 的全部
21 个启动失败场景；20 次确认 abort 后释放 net2 撤销记录，1 次 double-abort
的第二次 abort 失败后保留拒绝记录。child 从未产生启动标记，每次资源检查
以及最终 net-stop 后的资源基线均恢复。

新 native manifest SHA-256 为 `54780a207073b26b5138b4d5a5694a2d0a8f103e5e1340ef06b87feba3997e6d`，新 guest
raw report SHA-256 为 `5c9e2dcaec921814b226d36419d9499cb5f96c34e214511e56310b44aaace1ce`，ISO SHA-256 为
`0814136dffa91539b55ab8ad159ea061174d0996a4d04b066fdb05c09ca27001`。完整输入、输出、原 serial 和转换记录位于
`docs/reports/p1f_main_integration/`，由单独 flat manifest 覆盖。

## 合并边界

两个文本冲突都在 builder 接线，已同时保留 C catalog/launch/300s lease
metadata 与 F ClarkE metadata；它们都进入 source identity 和最终 manifest。
`user_build.py` 保留 D fixture 使用的原精确 selector，再合并 F strip-all
profile。新 native supervisor 剥离后为 115360 bytes，
未放宽 128 KiB image read limit；entry 与每个 PT_LOAD 属性和完整字节相等。

F 的 95 个路径中 88 个逐字节保留，7 个共享路径有主线整合：ABI registry、
两个 builder、loader、network core 的两份文件及 supervisor。K5 的
`spawn_options.transfer_independent_pipes=false` 和完整 opt-in 路径保留，
F 的 abort outcome 是独立 version1/32-byte 输出，未回退 K5 结构。
G Interactium 主线 service/dispatcher/window_manager/client 保持原字节，
F QPA 的 checkpoint6 reply-capacity decoder 保持原字节。I1 的 resolver
配置、六参数 DHCP callback 和服务循环接线保留；F net2 op21 仅按原设计
添加 controller 授权的 peer-policy 查询/retired release。

C owner 对两个 builder 的 metadata、profile 限制及 entry/PT_LOAD 校验做
限定只读复核，未发现具体阻断；没有改文件或重复测试。全局状态文档由 root
维护，本次不修改 `docs/state.md`。之后合入的 docs-only 状态更新应在最终
发布时保留，不改变本次 native 源身份。

## 旧产物与新镜像的身份

child 始终复用 609,008-byte 冻结 ELF，SHA-256
`a8fe1fc3cf5f3c0396ab63d7b5c9c6c34364858fe520f746b7c325dcc3a3660b`。原 child source/SDK/strip receipt、静态 C++ SDK
manifest/profile、lwIP 输入及历史 native/guest 回执等
10 项冻结输入全部通过 before/after 摘要核对。
源快照的 2726 项输入也逐项与 staging index、
原工作树和构建期间快照相同。没有重编 child、重建 GNU 或重新绑定 SDK。

本轮只证明旧 child 在新 native image 上的既有失败清理行为。它使用 K5
legacy 默认分支，不覆盖新 opt-in pipe transfer，不覆盖 I1 failover，也
不代表完整浏览器完成。`BAD_START_ENTRY` 仅属于本次专用 probe 镜像；
后续完整浏览器必须独立使用不带该 flag 的 `--clarke-bundle` 镜像。
原 child 首次 LOAD 内 ELF section-table metadata 的剥离差异仍由旧 receipt
明确记录，不能套用新 native supervisor 的全 PT_LOAD 字节相等声明。

## 实际执行与资源

SDK 启动保持默认网络 profile，仅显式传入认证 lwIP archive 和
`XOS_QMP_TRANSPORT=pipe`；native 命令为 `scripts/build.py` 加
`--quiet-demos-on-launch` / `--clarke-launch-probe`。runner 为冻结的
`tests/clarke_launch_guest.py`，SHA-256 `d75d0b48cb757e383b9eb3e12122207d410fc1d28db95c3b26c1ca9d4095809f`。
默认 net-start 41，地址 10.0.2.15/24、gateway 10.0.2.2、两个 resolver=0，
无 static/DHCP/DNS probe 开关。

冷资源 `[129673, 3, 1]` → 初始化
`[129672, 3, 1]`，第二普通启停仍为
`[129672, 3, 1]`。已初始化服务前后
`[129672, 3, 1]` / `[129672, 3, 1]` 完全相等。
元组顺序为 free pages、live tasks、completion records。首次 observer
页数单独实测记录，每个场景的接受门保持原样。

此前两次尝试仅在 host 编排前置检查失败：SDK 挂载无法解析 host Git
worktree metadata；以及原 builder 拒绝源树外的输出目录。两份原日志保留
并公开投影，没有启动 target 编译或 VM，不计入 21-case 正/负场景。
最终编排使用同一次 SDK invocation 的临时源快照及其 build/ 子目录，
既遵守原 builder 约束，也避免占用共享工作盘保存可重建对象。

## 证据与 diff 检查

公开路径检查读取实际 stage-zero index，对所有候选路径执行扫描，不排除
原报告或日志。源码与新证据的 whitespace 检查通过。无范围筛选的
`git diff --cached --check` 返回 2，发现的仅是 checkpoint6 自带的六份原始
serial 中的 CRLF / prompt 尾部空白；六个 blob 已逐项证实与原 F 提交相同。
因此保持这些原始证据字节，只在源码/新证据 whitespace 检查中精确排除
这六个文件，完整命令、原摘要和结果登记在 `diff_gate.json`。公开路径检查
仍扫描全部内容。没有通过规范化原始 serial 来改写历史证据。
