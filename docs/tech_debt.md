
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

## 一、架构债（宪法裁定的整改义务）

| # | 债项 | 规模 | 退出条件 | 依据 |
|---|---|---|---|---|
| A1 | **内核态驱动存量**：virtio_gpu+display / ata / ps2 | 256 + 131 + 108 行 | 设备授权原语落地 → 逐个迁用户态驱动服务，独立客体验收 | [0088](./work_log/0088_kernel_driver_c28_debt_register.md) |
| A2 | **设备授权原语**（**论证+登记已交 PR，实施待续**） | 1 个 ABI（`sys_device`=112，多路入口） | C20 论证与接口冻结已成文：[device_authorization_v1](./contracts/device_authorization_v1.md)（请求布局/11 操作/权利位/错误值全部冻结；DMA 终止序与 quarantine 成文；PIO 边界= sys82 线）。登记 PR 另含登记表 112–127 新段与 112 认领。实施已开工：段 1a（112 端到端接通+冻结头校验+客体负向探针 9/9，见0170）已交付；下一步=段 1b grant 表 → 显示迁移纵向切片 → ps2/ata（依赖 sys82 对齐）→ 网络 |
| A3 | debug_console 引导/调试例外 | 73 行 | 按 C26 登记随例外线处理（按设计存在，非欠账实为"记账资产"） | 0088 |

> 网络线（N2/TCP/HTTPS）按你指示不出账，仅留 A2 这条共同前置。

## 二、命名债（C30）

（无未清偿项：B1 已合并，B2 经用户裁决豁免。）

## 三、验收/证据债

| # | 债项 | 内容 |
|---|---|---|
| C4 | 冻结回执泄露宿主绝对路径（**已并入 Issue #37 线，本债转由该线跟踪**） | 处置以 [PR #56](https://github.com/Xiao-John/XylophoneOS/pull/56) 为准：10 份混合换行串口恢复原始字节（索引不重写，独立复核 10/10）、入库守卫扫描器 + 索引校验器、冻结报告 `-text` 泛化、work_log 命令模板化。全量字节脱敏尝试已停止并整体回滚，工具与说明留档 `perry_host_path_scrub_20261031`（NOT_COMPLETED/SUPERSEDED，新契约首个 compliant 目录）。残余历史暴露 = Issue #37 的 open 边界（git 对象已发布，需维护者评审的迁移），如实登记不宣称关闭 |
| C5 | work_log 撞号（**索引化清偿，本 PR 交付**；历史文件不动） | 采用"老人老办法"：不改任何历史文件名、零级联——新增 `docs/work_log/README.md` 编号索引，登记全部 12 组历史重复（含本轮扩围发现的 8 组未登记：0062/0063/0064/0065/0066/0073/0082/0088）并声明"自 0149 起编号唯一、新记录不得复用"；此前 4 组改号方案（0150–0153）因会把 5 个冻结清单拖入修改集、触发守门扫描器与级联螺旋而被否决回滚，过程记于 0154 |
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
| D7 | Qt | **许可面收口**（0189）：Qt 2 份上游文本入库登记（11→13）、LGPLv3 §4d0 对应源码/可重链接交付物成文（`src/ports/qt6/REDISTRIBUTION.md`+manifest）、10 补丁修改标注（`patches/MODIFICATIONS.md`）、GCC 运行库逐成员 **397/407**、Qt 逐成员映射见 `docs/reports/qt_member_license_20261103/`；newlib 1053/1053（0188）。**均为映射/材料审查、非法务意见，Qt 静态再分发资格仍 NOT_GRANTED**；全部残余（GCC 10 个未解析、Qt 残项、打包核验、安全审查、商业 N/A）逐条登记于 `licenses/open_items.json`。剩余=QML/Quick 未实现（未立项，功能线不阻塞发版） |
| D8 | 工具/发行 | ISO 通用载荷/空盘安装、日常工具逐命令资格、非 ASCII 大小写折叠、完整游戏流程、公开分发未验 |
| D9 | 音频 | AU0–AU5 仅文档 |
| D10 | 发行 | 0.0.2-1103 已定版（`VERSION` 已更新）但**未发布**，资产仍绑 1026 旧 build；冻结/打包/上传按 `docs/releases/next_release.md` 执行 |
| D11 | 启动/恢复门 | **无盘启动**时 files 客户端返回 `io`，supervisor 恢复门按 fail-closed 常开，xsh 仅剩白名单命令可用（`d6363f8`，2026-10-27 引入）。本轮经用户裁决只给 `task`/`process`/`libc` 三个 smoke 测试补挂临时工作盘绕开；"无盘（io）是否应视为无标记而放行"属设计语义，待按宪法原则裁决后再改门 |
| D12 | 构建/证据 | **归档成员来源实现债**：`docs/contracts/archive_member_provenance.md` 已立（下次重建起产出 `member_manifest.json`），但三份考古脚本（newlib/GCC/Qt）尚未抽成共享校验器 `scripts/archive_member_map.py`。退出条件=契约生效的首次重建同时落地共享实现，此后逐成员审计只读清单+跑校验 |
| D13 | Aurora Desktop | Studio 首跑间歇超时：同一二进制重跑通过、根因未明（PR #45 证据如实保留）；退出条件=定位根因或给出稳定复现/豁免判据 |
