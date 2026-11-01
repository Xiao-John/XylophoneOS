
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

## 一、架构债（宪法裁定的整改义务）

| # | 债项 | 规模 | 退出条件 | 依据 |
|---|---|---|---|---|
| A1 | **内核态驱动存量**：virtio_gpu+display / ata / ps2 | 256 + 131 + 108 行 | 设备授权原语落地 → 逐个迁用户态驱动服务，独立客体验收 | [0088](./work_log/0088_kernel_driver_c28_debt_register.md) |
| A2 | **设备授权原语**本身未设计/未登记（#18 帧代理已撤回） | 1 个 ABI | 按 C20 论证 + 登记 → 实施 | state.md 基线节 |
| A3 | debug_console 引导/调试例外 | 73 行 | 按 C26 登记随例外线处理（按设计存在，非欠账实为"记账资产"） | 0088 |

> 网络线（N2/TCP/HTTPS）按你指示不出账，仅留 A2 这条共同前置。

## 二、命名债（C30）

（无未清偿项：B1 已合并，B2 经用户裁决豁免。）

## 三、验收/证据债

| # | 债项 | 内容 |
|---|---|---|
| C2 | PR #21 遗留 4 项（**已交 [PR #55](https://github.com/Xiao-John/XylophoneOS/pull/55)，待合并后移入已清偿**） | "3/138"查实=138 份冻结证据仅 3 份被字节冻结覆盖 → 补 `**/-text` 整目录，check-attr 138/138；matrix 35 格写死结果 → 从冻结回执取真值、缺回执拒跑（30/35 逐字节同、5 格取真值、冻结 CSV 未动）；guest `compatibility_status` 按名写死 → 从真实退出码+标记推导（冻结日志复现 10/10）；pypdf source 钉版本+sha256 直链（哈希取自本仓冻结回执）。0148 记账 |
| C3 | PR #19 遗留 4 项（2026-10-31 逐项核销，**已交 [PR #55](https://github.com/Xiao-John/XylophoneOS/pull/55)，待合并后移入已清偿**） | ①历史回退卡死：**已修可核销**（0096 `da77f66`：`navigate` 返回 bool + 候选视图，`travel` 成功才提交 index），#39 后本机补跑 negative 18/18、interactive 10/10 PASS，含 `failed_engine_load_preserves_page_history_scroll_and_tabs`；②CSS 拒绝报错文案：**原仍未修，本轮修**——基线串口实测 linked/quota CSS 拒绝被报成 `Engine allocation or resource budget failed`，现 `view.hpp` 按异常 `what()` 映射为 `Stylesheet rejected` / `Stylesheet import quota exceeded`（`content.hpp:133` 同步去掉 "budget" 误称）；③virtio 适配器：**原仍未入仓，本轮补**——冻结件只留 `executed_sha256=5cf2b9a3…`（≠在仓 runner `57a4e153…`），`src/` 内的 virtio 仅是内核驱动（属 A1），现把 `--backend virtio` 写进 `tests/aurora_browser_acceptance.py` 并实跑 PASS（串口 `[display] backend=virtio-gpu-2d`）；④契约措辞：**0096 已如实但已过时，本轮改**——原“尚未跑”与 g3 `browser-negative` PASSED 矛盾，改为实证引用并把 16 条历史/4 tab/峰值长压明确标未实测。证据 [0148](./work_log/0148_c2_c3_debts_and_localpilot_rules.md) |
| C4 | 冻结回执泄露宿主绝对路径（**已并入 Issue #37 线，本债转由该线跟踪**） | 处置以 [PR #56](https://github.com/Xiao-John/XylophoneOS/pull/56) 为准：10 份混合换行串口恢复原始字节（索引不重写，独立复核 10/10）、入库守卫扫描器 + 索引校验器、冻结报告 `-text` 泛化、work_log 命令模板化。全量字节脱敏尝试已停止并整体回滚，工具与说明留档 `perry_host_path_scrub_20261031`（NOT_COMPLETED/SUPERSEDED，新契约首个 compliant 目录）。残余历史暴露 = Issue #37 的 open 边界（git 对象已发布，需维护者评审的迁移），如实登记不宣称关闭 |
| C5 | work_log 撞号（**索引化清偿，本 PR 交付**；历史文件不动） | 采用"老人老办法"：不改任何历史文件名、零级联——新增 `docs/work_log/README.md` 编号索引，登记全部 12 组历史重复（含本轮扩围发现的 8 组未登记：0062/0063/0064/0065/0066/0073/0082/0088）并声明"自 0149 起编号唯一、新记录不得复用"；此前 4 组改号方案（0150–0153）因会把 5 个冻结清单拖入修改集、触发守门扫描器与级联螺旋而被否决回滚，过程记于 0154 |
| —（制度新增，非债） | 证据完整性契约 | [evidence_integrity.md](./contracts/evidence_integrity.md)：git commit 为唯一信任根；新报告目录平铺 `manifest.json` 根清单、叶子互不哈希、修改只动两处；存量老人老办法；`tests/report_manifest_check.py` 如实报 compliant/grandfathered |

## 四、功能/范围债（state.md 快照口径，细目在各 work_log）

| # | 线 | 缺口 |
|---|---|---|
| D1 | xypm | P3 未开工（完整事务、签名仓库） |
| D2 | ncursesw | W0 未冻结、W1 未实现/未验收 |
| D3 | 故障包 | FB3/FB4、任意断电安全、全局收集、寄存器/栈快照 |
| D4 | Pillow 线程 | **BLOCKED**：dash worker newlib `_malloc_r` vector14 未解 |
| D5 | 现代应用 | Web 能力/应用化 BLOCKED |
| D6 | 平台 | 系统重建/自举未验、SMP 未验、绝对峰值未测 |
| D7 | Qt | QML/Quick 未做、静态分发未审、**逐成员许可审计未完** |
| D8 | 工具/发行 | ISO 通用载荷/空盘安装、日常工具逐命令资格、非 ASCII 大小写折叠、完整游戏流程、公开分发未验 |
| D9 | 音频 | AU0–AU5 仅文档 |
| D10 | 发行 | 0.0.1-1026 后未发新 Release，资产绑旧 build |
