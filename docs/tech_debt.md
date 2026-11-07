
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
| A2 | **设备授权原语**（**论证+登记已交 PR，实施待续**） | 1 个 ABI（`sys_device`=112，多路入口） | C20 论证与接口冻结已成文：[device_authorization_v1](./contracts/device_authorization_v1.md)（请求布局/11 操作/权利位/错误值全部冻结；DMA 终止序与 quarantine 成文；PIO 边界= sys82 线）。登记 PR 另含登记表 112–127 新段与 112 认领。实施已开工：段 1a（112 端到端接通+冻结头校验+客体负向探针 9/9，见0170）已交付；下一步=段 1b grant 表 → 显示迁移纵向切片 → ps2/ata（依赖 sys82 对齐）→ 网络 |
| A3 | debug_console 引导/调试例外 | 73 行 | 按 C26 登记随例外线处理（按设计存在，非欠账实为"记账资产"） | 0088 |

> 网络线（N2/TCP/HTTPS）按你指示不出账，仅留 A2 这条共同前置。

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
| D4 | Pillow 线程 | **BLOCKED**：dash worker newlib `_malloc_r` vector14 未解 |
| D5 | 现代应用 | Web 能力/应用化 BLOCKED |
| D6 | 平台 | 系统重建/自举未验、SMP 未验、绝对峰值未测 |
| D7 | Qt | **许可面收口**（0189）：Qt 2 份上游文本入库登记（11→13）、LGPLv3 §4d0 对应源码/可重链接交付物成文（`src/ports/qt6/REDISTRIBUTION.md`+manifest）、10 补丁修改标注（`patches/MODIFICATIONS.md`）、GCC 运行库逐成员 **397/407**、Qt 逐成员映射见 `docs/reports/qt_member_license_20261103/`；newlib 1053/1053（0188）。**均为映射/材料审查、非法务意见**；B4 打包核验与 B5 安全审查已于 2026-11-04 执行并闭合，Qt 静态交付物随 0.0.2-1103 分发；残余见 `licenses/open_items.json`（商业 N/A 等）。#67/#68 已合入 main，`open_items.json` 审计闸门生效。剩余=QML/Quick 未实现（未立项，功能线不阻塞发版） |
| D8 | 工具/发行 | ISO 通用载荷/空盘安装、日常工具逐命令资格、非 ASCII 大小写折叠、完整游戏流程、公开分发未验 |
| D9 | 音频 | AU0–AU5 仅文档 |
| D10 | 发行 | **0.0.2-1103 已发布**（2026-11-04，含 Qt 资产；smoke 11/11）；1026 历史可下载。下次发版按 playbook/release_pipeline.sh |
| D11 | 启动/恢复门 | **无盘启动**时 files 客户端返回 `io`，supervisor 恢复门按 fail-closed 常开，xsh 仅剩白名单命令可用（`d6363f8`，2026-10-27 引入）。本轮经用户裁决只给 `task`/`process`/`libc` 三个 smoke 测试补挂临时工作盘绕开；"无盘（io）是否应视为无标记而放行"属设计语义，待按宪法原则裁决后再改门 |
| D12 | 构建/证据 | **归档成员来源实现债**：`docs/contracts/archive_member_provenance.md` 已立（下次重建起产出 `member_manifest.json`），但三份考古脚本（newlib/GCC/Qt）尚未抽成共享校验器 `scripts/archive_member_map.py`。退出条件=契约生效的首次重建同时落地共享实现，此后逐成员审计只读清单+跑校验 |
| D13 | Aurora Desktop | Studio 首跑间歇超时：同一二进制重跑通过、根因未明（PR #45 证据如实保留）；退出条件=定位根因或给出稳定复现/豁免判据 |
| D14 | SSG P3B/P3C | **竞态与限定验收挂账**（#50/#51 合并时按披露接受，不阻塞合入）：`EXIT_RACE_ROOT_CAUSE=UNRESOLVED`（consumer-exit timeout ×2、Notes shutdown 竞态根因未明）；早期 stress **23/24** 不回溯升级；P3C 仅 scoped requalification（32 contract checks + 独立 guest verifier，旧构建 24/24 stress 未在合入 head 重跑）；`globalAtomicSnapshot=NOT_IMPLEMENTED`、`DISTRIBUTION_NOT_QUALIFIED`。退出条件=定位竞态根因或给出豁免判据 + 在合入后 main head 重跑完整 stress 并留证 |

## 六、盲测遗留（2026-11-05，0.0.2-1103 第三方盲测）

| 编号 | 分类 | 债项 | 证据 / 退出条件 |
|---|---|---|---|
| BT-01 | BUG/UX | 嵌套 dash 的 fork 拒绝：直接由 `xsh>` 启动的 dash 可 fork；dash 内再启动 dash 后，命令替换报 `fork: Not owner`。公开文档未说明嵌套 shell 不继承构造权。 | 盲测 `qemu_session.log`；退出条件=明确这是权限边界并写入 dash 文档，或修复为可预期的错误/降级。 |
| BT-02 | UX | `diag` 无参数时报 `xsh: diag: not found`，没有 usage；`diag` 是 builtin，错误会误导。 | 盲测 `qemu_session.log`；退出条件=无参数打印 `Usage: diag <program> [args]` 并返回明确状态，补 usage 文档。 |
| BT-03 | DOC/UX | `/bin` 在 PATH 和部分示例中出现，但发行工作盘没有 `/bin`；`ls /bin` 报 `[files] list error=-1`。 | 盲测 `ls /bin`、`echo $PATH`；退出条件=建立 `/bin`、移除 PATH 中不存在的项，或同步修改所有示例。 |
| BT-04 | UX | CPython 每次启动打印 `Could not find platform dependent libraries <exec_prefix>`；核心功能可用但首次使用者会误判安装损坏。 | 盲测 Python 多文件项目；退出条件=设置正确的 exec_prefix/移除该警告，或在公开文档解释。 |
| BT-05 | DOC/可发现性 | `xos-diag` 默认不装入发行工作盘，公开入口和 `dash` 内都没有可执行文件；当前文档要求从构建产物手工安装。盲测 K 因此无法完成。 | `docs/usage/userland/dash.md`、客体 `/usr/bin`；退出条件=把 `xos-diag` 纳入发行载荷，或提供正式、可审计的安装包并在 README 指向。 |
| BT-06 | 语义限制 | `clock()` 修复为单调墙钟（首次调用起，1000 Hz）；XOS 当前没有 per-process CPU accounting，因此 `clock()` 不是严格的进程 CPU 时间。 | `src/user/libc/newlib_syscalls.cpp`；退出条件=引入进程 CPU tick 统计并把 `_times` 改为真实 user/system time。 |
| BT-07 | 发行 | `v0.0.2-1103` 已发布的 SDK 资产早于 P0/P1 XYPm 修复；磁盘上的源码/新构建 SDK 与下载资产不一致。 | PR #85 / XYPm 调查；退出条件=重新打包 SDK、更新校验清单，或发后续 patch release。 |
| BT-08 | UX/诊断 | `-ftime-report` 的 guest clock 曾输出约 516 年、百分比超过 100%；本次已修 `_times`，但既有发布编译器二进制不会因源码修复自动更新。 | `build/cpp_link_investigation/session.log`；退出条件=重建并发布编译器/SDK 后复测。 |

## 七、文件服务 POSIX 子集债（2026-11-07，found_bug 修复过程中确认）

| 编号 | 分类 | 债项 | 证据 / 退出条件 |
|---|---|---|---|
| FS-01 | 语义 | 同一文件已有写打开时，再 `open`（读或写）返回 `busy`：FatFs `FF_FS_LOCK=32` 用它防止两个 `FIL` 的目录项互相覆盖。POSIX 允许同一文件多个打开；当前只有 `dup`/fork 共享描述。 | `src/third_party/fatfs/ffconf.h`、`tests/fixtures/file_posix/file_posix.c`；退出条件=按 inode 共享描述或实现多 `FIL` 的目录项协调后放开锁。 |
| FS-02 | 语义 | `rename` 只替换普通文件；目录→已存在空目录、目录跨父目录替换均不支持（返回 EEXIST），目录移入自身后代已明确拒绝。 | `src/user/services/files.cpp` `op::rename`；退出条件=按 POSIX 目录替换语义实现并覆盖短名别名测试。 |
| FS-03 | 验证 | `ftruncate` 扩大与满盘路径只用注入短写验证了“返回 no_space 并回滚长度”，未在真实满盘介质上端到端复现；回滚本身是 best effort，失败会置 recovery gate。 | `tests/file_semantics.py` 第 11 组；退出条件=专用近满 FAT 镜像客体测试。 |
| FS-04 | 语义 | 有打开实例的文件不能 `unlink`/`rename`（返回 `busy`）；POSIX 允许删除已打开文件并延迟释放。 | `src/user/services/files.cpp` `op::remove`/`op::rename`；退出条件=引用计数 + 延迟删除。 |
| FS-05 | 性能 | libc 路径解析对每个中间分量发一次 `stat` RPC，无缓存；深路径的 `open/stat` 会比原先多若干次 IPC。 | `src/user/libc/newlib_syscalls.cpp` `resolve_path_from`；退出条件=确认开销不可接受时加 cwd 相对缓存或服务端逐分量解析。 |
| FS-07 | 性能 | `ftruncate`/写越界必须真实写零才能避免泄露旧簇；扩大到大文件时成本与新增长度线性，FAT 没有可安全使用的稀疏表示。 | `src/user/services/files.cpp` `zero_fill`；退出条件=确认大文件场景实际需要后，评估按簇清零或专用格式化路径。 |
| FS-06 | 授权边界 | 句柄转移现在要求内核认证的 `parent_pid` 等于调用者；父进程仍可向自己的子进程注入并耗尽其 `max_open`，这是创建者权限内的行为，未引入显式接受令牌。 | `src/kernel/arch/x86_64/tasks.cpp` `sys_file_session`、`src/user/services/files.cpp` `op::transfer`；退出条件=需要更强隔离时引入目标接受/能力令牌。 |
