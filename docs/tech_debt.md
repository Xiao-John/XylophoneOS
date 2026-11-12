
# XOS 技术债总账（2026-10-30，PR #20 集群除外）（本账本自 2026-11-01 起入库跟踪，多线共见共还；更新随分支/PR 交付）

## 近期已清偿 ✅

| 债 | 清偿方式 |
|---|---|
| `pic_eoi` 计时耦合、三套时基 | C29 入宪 + #33 统一时基落地 |
| #29 五个自研类名违规 | C30 改名 + 纯度证明（0112 补件） |
| state.md 合并战场（245 行） | PR #36 快照制已合（`ca2e372`） |
| CSV 证据归一化信任倒置 | 已修（字节恢复到原哈希） |
| C30 入宪程序 | 已完成（v1.5） |
| **B1 十五个自研 CamelCase 类名**（2026-10-31） | [PR #39](https://github.com/Xiao-John/XylophoneOS/pull/39) 已合并：`ac8160d` 纯改名字节恒等证明 + `c938bf6` 限定修复；验收 0145 + `aurora_c30_rename_b1_20261031` 五件套（其 NOT_RUN 转 C6 续偿） |
| **B2 两个 QPA 上游强制名**（2026-10-31） | 用户裁决豁免（C30 上游接口强制兼容例外）：`QEventDispatcherXos`/`QXosIntegrationPlugin` 不改名 |
| **C6 B1 改名客体验收**（2026-10-31） | [PR #52](https://github.com/Xiao-John/XylophoneOS/pull/52) 已合并（`8ec0489`）：四套客体套件本机全 PASS（standard_button 3/3、render 13/13、semantic 5/5、ssg_diff 13/13）+ 宿主 blur 396+6；qxos.moc 目标再生成；证据 `c6_guest_requal_20261031`、0146 记账；随组修复 0009/0010 补丁、`::fonts`、ssg 期望值 12→13 |
| **C1 #29 修复③④客体再验收**（2026-10-31） | [PR #53](https://github.com/Xiao-John/XylophoneOS/pull/53) 已合并：C6 实跑清单与 0112 欠账逐一对应且基线含修复；另补纳秒粒度探针 `delta_ns=20583`；0147 记账 |
| **C2 PR #21 遗留 4 项**（2026-11-01） | [PR #55](https://github.com/Xiao-John/XylophoneOS/pull/55) 已合并：冻结覆盖 138/138（`**/-text` 整目录）、matrix 30/35 逐字节同 + 5 格取真值缺回执拒跑、guest `compatibility_status` 按真实退出码推导（10/10）、pypdf source 钉版本+sha256 直链；0148 记账 |
| **C3 PR #19 遗留 4 项**（2026-11-01） | [PR #55](https://github.com/Xiao-John/XylophoneOS/pull/55) 已合并：历史回退卡死修复（0096 `da77f66`）、CSS 拒绝报错文案按异常 `what()` 映射、`--backend virtio` 入 `tests/aurora_browser_acceptance.py` 并实跑 PASS、0096 契约措辞改为实证引用；0148 记账 |
| **D2 ncursesw W0/W1**（2026-11-03） | [PR #66](https://github.com/Xiao-John/XylophoneOS/pull/66) 已合并：W0 终验冻结（12 项 `xsh_*` gate，`build/w1_final_acceptance/frozen/`）、W1 最终验收全 gate 通过（4 系统 + 15 项终端交接探针 + 宽字符一致性 + 客体探针）；0187 记账 |
| **SSG 批次 work_log 撞号**（2026-11-04） | PR #40/#44–#51 合并战役中统一让号 **0190–0197** 并逐 PR 重建 `work_log/README.md` 索引；历史 0103 改名按 C5 撤销；#47 漏插 0193 行补回 |
| **SSG 批次承载面 C30**（2026-11-04） | #50/#51 合并时清零 `Baseline*`/`Client`/`NotesBaseline`/`PairObservation`/`Source`/`DiffStatus`/`xosSsgProtected` 等（对齐主线 snake_case 类型），watch 层 `watch_adapters` 一并改名 |
| **C30-存量-01 file_client**（2026-11-04） | `xos::file::Client`→`xos::file::client`（27 文件；mangled `file6Client`→`file6client` 同步 fb0/save_failures asm 与 `--wrap`；冻结报告历史符号不改）；0198 记账 |
| **C7 证据冗余**（2026-11-04） | 按 §4 语义修订：删 consumers 侧同 sha `browser-dom-first.png`（保留 bfi 血统引用侧）+ 两目录 `serial.log.gz` 双份；4 份 manifest 重生成；`browser-dom-reload.png` 同 sha 与全仓 serial 双写惯例属范围外观察；0198 记账 |

## 一、架构债（宪法裁定的整改义务）

| # | 债项 | 规模 | 退出条件 | 依据 |
|---|---|---|---|---|
| A1 | **内核态驱动存量**：virtio_gpu+display / ata / ps2 | 256 + 131 + 108 行 | 设备授权原语落地 → 逐个迁用户态驱动服务，独立客体验收 | [0088](./work_log/0088_kernel_driver_c28_debt_register.md) |
| A2 | **设备授权原语：实现已交付，客体未验**（2026-11-12） | sys112 grant、MMIO、连续 DMA、IRQ、撤销/退出与用户态 VirtIO-net 原始帧纵切 | 仅 supervisor 的 owned building child 可获授权；真实硬件/guest 未验。无 IOMMU，未证实 reset 的 DMA 仍 quarantine。显示/PS2/ATA 全迁移与完整网络仍待实施。 | [设备契约](contracts/device_authorization_v1.md)、[网络契约](contracts/net_user_driver.md)、[07374f76](work_log/07374f76_ipc_device_network_runtime.md) |
| A3 | debug_console 引导/调试例外 | 73 行 | 按 C26 登记随例外线处理（按设计存在，非欠账实为"记账资产"） | 0088 |

> 网络原始帧纵切随 A2 实装；N2/TCP/HTTPS 不在本轮实现结果中。

## 二、命名债（C30）

（无未清偿项：B1 已合并，B2 经用户裁决豁免；SSG 批次承载面 C30 已于 #50/#51 合并时清零；C30-存量-01 `file_client` 已于 2026-11-04 清偿，见 0198。）

## 三、验收/证据债

| # | 债项 | 内容 |
|---|---|---|
| C4 | 冻结回执泄露宿主绝对路径（**已放掉**，2026-11-04 用户裁决） | 用户关闭 Issue #37 并裁决放掉：现版本无真隐私路径即可。全树 `CONFIRMED_PRIVATE_PATH` 仅 3 条且均已复核在案：`tests/seed_diagnostics_cases.py` 与 `litehtml-0.9.tar.gz` 归档成员由 `reviewed_synthetic_paths.json` 登记 `SYNTHETIC_FIXTURE`（合成诊断串/上游打包残留，扫描器不绕过、findings 如实保留）；我方源码无真实贡献者路径。absolute_command/private_temp 类为可移植性/证据保真范畴非隐私债。历史处置（PR #56 守卫扫描器等）继续有效 |
| C5 | work_log 撞号（**索引化清偿，本 PR 交付**；历史文件不动） | 采用"老人老办法"：不改任何历史文件名、零级联——新增 `docs/work_log/README.md` 编号索引，登记全部 12 组历史重复（含本轮扩围发现的 8 组未登记：0062/0063/0064/0065/0066/0073/0082/0088）并声明"自 0149 起编号唯一、新记录不得复用"；此前 4 组改号方案（0150–0153）因会把 5 个冻结清单拖入修改集、触发守门扫描器与级联螺旋而被否决回滚，过程记于 0154 |
| C7 | SSG 批次证据冗余（**已清偿**，2026-11-04 按 §4 落地） | 已删 consumers 侧同 sha `browser-dom-first.png`（bfi 血统引用侧保留）与两目录 `serial.log.gz` 双份，4 份 manifest 重生成，`report_manifest_check` passed；语义修订记录见 0198。范围外观察：`browser-dom-reload.png` 同 sha、全仓 serial 双写历史惯例（含冻结件）——未立债 |
| —（制度新增，非债） | 证据完整性契约 | [evidence_integrity.md](./contracts/evidence_integrity.md)：git commit 为唯一信任根；新报告目录平铺 `manifest.json` 根清单、叶子互不哈希、修改只动两处；存量老人老办法；`tests/report_manifest_check.py` 如实报 compliant/grandfathered |

## 五、例外登记（C26）

| 登记号 | 例外内容 | 必要性 | 范围 | 负责人 | 退出条件 | 确认 |
|---|---|---|---|---|---|---|
| C26-2026-11-01-01 | 冻结证据就地脱敏（"不移动改写"的例外） | 守门扫描在主线冻结件中实测 442 条个人路径 findings（含 27 处真实 macos_home），隐私与第三方复核障碍（Issue #37） | `docs/reports/` 下本 PR 所改 586 个文件的路径替换（35 份 old_sha→new_sha 账本，`verify_evidence_migration.py` 字节级可复现）+ 17 个冻结目录新增 `SANITIZED_EXPORT.md` 指针（仅指针，不改其账本） | www080327-glitch（Issue #37 线） | ① 全树分类 OPEN 清零；② `check_public_evidence_paths` 转 PUBLIC_READY；③ 迁移后冻结件仅允许机械替换与本例外登记范围内的操作 | 用户已确认（2026-11-01，PR #60 评审线程） |

## 四、功能/范围债（state.md 快照口径，细目在各 work_log）

| # | 线 | 缺口 |
|---|---|---|
| D1 | xypm | P3 未开工（完整事务、签名仓库） |
| D3 | 故障包 | FB3/FB4、任意断电安全、全局收集、寄存器/栈快照 |
| D4 | Pillow 线程 | **UNRESOLVED**：旧 dash worker 的 newlib `_malloc_r` vector14 根因未定位；已核对 TLS、锁、sbrk、退出和历史回执，缺原故障 ELF/线程 archive/堆现场，不能用宿主 Pillow 代验。定位边界见 [9e72a804](work_log/9e72a804_ssg_deadlines_lifecycle_review.md)。 |
| D5 | 现代应用 | Web 能力/应用化 BLOCKED |
| D6 | 平台 | 系统重建/自举未验、SMP 未验、绝对峰值未测 |
| D7 | Qt | **许可面收口**（0189）：Qt 2 份上游文本入库登记（11→13）、LGPLv3 §4d0 对应源码/可重链接交付物成文（`src/ports/qt6/REDISTRIBUTION.md`+manifest）、10 补丁修改标注（`patches/MODIFICATIONS.md`）、GCC 运行库逐成员 **397/407**、Qt 逐成员映射见 `docs/reports/qt_member_license_20261103/`；newlib 1053/1053（0188）。**均为映射/材料审查、非法务意见**；B4 打包核验与 B5 安全审查已于 2026-11-04 执行并闭合，Qt 静态交付物随 0.0.2-1103 分发；残余见 `licenses/open_items.json`（商业 N/A 等）。#67/#68 已合入 main，`open_items.json` 审计闸门生效。剩余=QML/Quick 未实现（未立项，功能线不阻塞发版） |
| D8 | 工具/发行 | ISO 通用载荷/空盘安装、日常工具逐命令资格、非 ASCII 大小写折叠、完整游戏流程、公开分发未验 |
| D9 | 音频 | AU1/AU2 已有 PC Speaker 租约、用户态单音服务和命令实现（0221/0222）；客体音频输出、服务恢复与 AU3–AU5 仍待验收/实施。不能继续按“仅文档”处理，也不能视为已通过端到端验收。 |
| D10 | 发行 | **0.0.2-1103 已发布**（2026-11-04，含 Qt 资产；smoke 11/11）；1026 历史可下载。下次发版按 playbook/release_pipeline.sh |
| D11 | 启动/恢复门 | **无盘启动**时 files 客户端返回 `io`，supervisor 恢复门按 fail-closed 常开，xsh 仅剩白名单命令可用（`d6363f8`，2026-10-27 引入）。本轮经用户裁决只给 `task`/`process`/`libc` 三个 smoke 测试补挂临时工作盘绕开；"无盘（io）是否应视为无标记而放行"属设计语义，待按宪法原则裁决后再改门 |
| D12 | 构建/证据 | **构建时捕获已实现，完整目标重建未验（2026-11-12）**：实际 compiler invocation、source/object/member 字节捕获已接入 newlib/GCC/Qt/双 SDK；SDK 导入保留原始 build id，license/release gate 校验覆盖。历史 derived 报告不升级；普通 SDK 的 legacy libc/libm 明示。宿主真实 cc/ar 回归通过，目标重建/Qt CMake hooks 尚未运行。见 [14a518fa](work_log/14a518fa_audit_followthrough_runtime_build_gui.md)。 |
| D13 | Aurora Desktop | **UNRESOLVED**：原 Studio 套件超时实际发生在后段 legacy Qt probe 的 `QT_WIDGETS_OK` 之后，事件循环与 input join 已结束；已缩小到对象析构/运行库退出区间，但缺阻塞栈，不能判定根因。见 [9e72a804](work_log/9e72a804_ssg_deadlines_lifecycle_review.md)。 |
| D14 | SSG P3B/P3C | **竞态与限定验收挂账**（#50/#51 合并时按披露接受，不阻塞合入）：`EXIT_RACE_ROOT_CAUSE=UNRESOLVED`（consumer-exit timeout ×2、Notes shutdown 竞态根因未明）；早期 stress **23/24** 不回溯升级；P3C 仅 scoped requalification（32 contract checks + 独立 guest verifier，旧构建 24/24 stress 未在合入 head 重跑）；`globalAtomicSnapshot=NOT_IMPLEMENTED`、`DISTRIBUTION_NOT_QUALIFIED`。2026-11-12 已修独立的迟到 ACK/传输期限问题（真实传输函数 20/20），但没有根因证据将其等同于本债。退出条件=定位竞态根因或给出豁免判据 + 在合入后 main head 重跑完整 stress 并留证；见 [9e72a804](work_log/9e72a804_ssg_deadlines_lifecycle_review.md)。 |

## 六、盲测遗留（2026-11-05，0.0.2-1103 第三方盲测）

| 编号 | 分类 | 债项 | 证据 / 退出条件 |
|---|---|---|---|
| BT-01 | BUG/UX | **主线已通过 SL1/SL2 改为创建权继承**，旧盲测的名称特判与深度委派行为已过期；本轮不重复实施。 | [SL1](work_log/0216_sl1_create_authority.md)、[SL2](work_log/0217_sl2_shell接入.md)；当前修订的完整客体复验仍受固定工具链限制。 |
| BT-02 | UX | **源码已修，客体待验（2026-11-12）**：裸 `diag` 打印 `Usage: diag <program> [args]`，不再落入外部程序查找。 | 已补 `tests/shell_launch_sl3.py` 用例；本轮未运行客体，见 [审计说明](reports/comprehensive_audit_20261112/README.md)。 |
| BT-03 | DOC/UX | **打包流程已补 `/bin`（2026-11-12）**；已发布旧镜像仍不含该目录。 | `scripts/package_release.py`、`scripts/release_smoke.py`；退出条件=在下次实际发行镜像运行新 release smoke。 |
| BT-04 | UX | **公开用法已解释（2026-11-12）**：静态 CPython profile 的 `exec_prefix` 启动提示不等同于模块导入成功或失败；提示本身尚未消除。 | [Python 用法](usage/userland/python.md#启动时的-exec_prefix-提示) 说明安装路径、如何检查实际结果，以及真实导入错误的区别；重新配置和重建解释器仍可后续处理。 |
| BT-05 | DOC/可发现性 | **下一次打包默认加入 xos-diag（2026-11-12）**：冻结 ELF 并验证 system manifest 后安装 `/usr/bin/xos-diag`；旧已发布镜像未变。 | freeze/package/smoke 与使用文档已同步；退出条件=完整构建并跑下一次发行验收，不能将源码改动冒充已发布。 |
| BT-06 | 语义实现/客体未验 | **已实现真实 CPU 记账（2026-11-12）**：sys89 返回进程 user/system、当前线程和已等待子进程 CPU 时间；`_times`/`times`/`clock` 与 pthread CPU clock 接入。 | 真实记账/时间桥宿主回归通过；单 CPU TSC 校准及目标运行尚未验收，不能将旧发布二进制视为已更新。见 [6bd8c261](work_log/6bd8c261_vm_cow_runtime_cpu_accounting.md)。 |
| BT-07 | 发行 | `v0.0.2-1103` 已发布的 SDK 资产早于 P0/P1 XYPm 修复；磁盘上的源码/新构建 SDK 与下载资产不一致。 | PR #85 / XYPm 调查；退出条件=重新打包 SDK、更新校验清单，或发后续 patch release。 |
| BT-08 | UX/诊断 | `-ftime-report` 的 guest clock 曾输出约 516 年、百分比超过 100%；本次已修 `_times`，但既有发布编译器二进制不会因源码修复自动更新。 | `build/cpp_link_investigation/session.log`；退出条件=重建并发布编译器/SDK 后复测。 |

## 七、文件服务 POSIX 子集债（2026-11-07，found_bug 修复过程中确认）

| 编号 | 分类 | 债项 | 证据 / 退出条件 |
|---|---|---|---|
| FS-01 | 语义实现/客体未验 | **已实现共享 file identity**：每对象唯一 FatFs FIL，独立 open 各有 offset，dup/fork 共享 open description，允许多读写打开；显式 loader pin 保持可执行字节稳定。 | 真实 files/FatFs 与 libc→SDK→service 宿主链通过；固定目标/客体未运行。见 [file_identity](contracts/file_identity.md)。 |
| FS-02 | 语义实现/客体未验 | **已实现空目录替换与跨父目录移动**，含短名/长名别名及祖先检查。 | 真实 FAT 宿主回归通过；目标客体未运行。见 [b8e04c2a](work_log/b8e04c2a_posix_file_identity.md)。 |
| FS-03 | 验证 | 近满 FAT16 介质生成器与 guest fixture 已实现，真实宿主介质验证保留一簇；客体满盘扩大/回滚未运行。回滚失败仍进入 recovery gate。 | `tests/fixtures/file_semantics/prepare_near_full.cpp` 与 `tests/file_identity_guest.py`；固定客体端到端通过后才能关闭验证欠账。 |
| FS-04 | 语义实现/客体未验 | **已实现打开文件 rename/unlink 与延迟删除**：服务保留对象引用，原路径与已打开实例分离，最后引用关闭才回收 backing。 | 真实 FatFs identity/recovery 回归通过；不宣称任意 FAT 断电原子性。见 [file_identity](contracts/file_identity.md)。 |
| FS-05 | 性能/客体未测 | 相对路径已交服务端按 cwd identity 解析，增加 wire v2 resolve_path，不再逐中间分量发 libc stat RPC。 | 源码与真实宿主链已覆盖；实际深路径延迟/缓存收益未测，不凭猜测新增缓存。 |
| FS-07 | 性能 | `ftruncate`/写越界必须真实写零才能避免泄露旧簇；扩大到大文件时成本与新增长度线性，FAT 没有可安全使用的稀疏表示。 | `src/user/services/files.cpp` `zero_fill`；退出条件=确认大文件场景实际需要后，评估按簇清零或专用格式化路径。 |
| FS-06 | 授权边界 | 句柄转移现在要求内核认证的 `parent_pid` 等于调用者；父进程仍可向自己的子进程注入并耗尽其 `max_open`，这是创建者权限内的行为，未引入显式接受令牌。 | `src/kernel/arch/x86_64/tasks.cpp` `sys_file_session`、`src/user/services/files.cpp` `op::transfer`；退出条件=需要更强隔离时引入目标接受/能力令牌。 |
| FS-08 | 语义实现/客体未验 | **cwd 已绑定目录 identity**：rename 后相对路径跟随，删除重建不会切到新目录；被删 cwd 保留 detached 身份。spawn/fork/exec 继承与 nullable startup 编码已修。 | 实际 libc/loader 与文件服务回归通过；客体 inherited-cwd、dash 多层继承待运行。见 [file_identity](contracts/file_identity.md)。 |
