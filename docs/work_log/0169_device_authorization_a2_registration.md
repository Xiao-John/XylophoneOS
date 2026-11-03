# 0169 设备授权原语 A2：C20 论证与 ABI 登记

2026-11-01 · 分支 `codex/device_authorization_a2_20261101`（基线 `bd73f61`）。

## 1. 范围与产物

- 清偿 `docs/tech_debt.md` A2 的"论证 + 登记"半程：
  - 新契约 [device_authorization_v1](../contracts/device_authorization_v1.md)：
    C20 论证成文（现有 65/66 单设备接口与 spawn-only 28 不足、调用主体/授权依据/
    生命周期/失败行为/架构假设逐项）；接口全冻结——64 字节请求布局、11 个操作编码、
    4 个权利位、12 个错误值（负 i64，按 ABI 命名空间）、输出字段、对象模型、
    IRQ/时间语义、撤销终止序（DMA 停止证据 → quarantine，C25 UNKNOWN 诚实）。
  - [abi_registry](../contracts/abi_registry.md)：新设 reserved 段 **112–127 设备授权线**，
    认领 **112 `sys_device`**（claimed；登记不生成源码常量或能力，实施另开 PR）。
  - [network_device_v1_proposal](../contracts/network_device_v1_proposal.md) 头部加
    "已被登记吸收、冲突以契约为准"指针（提案保留为推导记录，未删除）。
  - 账本 A2 行更新为"论证+登记已交 PR，实施待续"。
- 明确边界：**PIO 不属本线**（= pio_grant/sys82 在途线），但该线 IRQ4 依赖本契约
  的 IRQ 操作——依赖关系写进契约 §1/§8；实施路线（内核原语 → 显示纵向切片 →
  ps2/ata → 网络）写进 §7，每步独立 PR + 独立客体验收（0088 退出条件）。

## 2. 选择与原因

- 单入口多路 syscall（提案的 64 字节请求布局本就是为此设计）而非 11 个 syscall：
  快照-校验-执行单点，错误优先级统一，登记规模与账本"1 个 ABI"一致。
- 编号从 112 起新设段而非借用 80–95 系统底座段：段义清晰、互不越界，
  符合"扩大范围亦须明确登记"。
- 错误值风格对齐既有 file/thread ABI（负 i64 + 按契约命名空间），不发明新风格。

## 3. 执行的命令与证据

- 事实来源：`network_device_v1_proposal.md`（布局/操作/终止序原文）、0088 存量登记
  （三驱动 495 行与退出条件）、`pio_grant.md`（在途 sys82 的边界与 IRQ4 依赖）、
  `thread_abi.hpp`/`file_abi.hpp`（错误值风格）、abi_registry 段表与认领规则。
- 校验：`tests/abi_doc_consistency.py`（段连续、认领格式与 reserved 段匹配、无重号）、
  `tests/docs_consistency.py`、`git diff --check`（见 PR）。

## 4. 通过 / 失败 / 未运行

- 通过：见 PR 检查清单。
- 未运行：无实现可跑——本组纯登记；内核原语与任何客体验收均 NOT_RUN（契约 §7 路线
  未开工），登记不生成任何源码常量或能力（registry 规则）。

## 5. 下一步

- 用户 review/合并登记 PR；合并后 A2 半程出账（实施半程按 §7 逐步开 PR）。
- 协调：pio_grant 线（sys82）合入时以本契约为 IRQ 通用出口；webengine M3 等待
  步骤 5（网络驱动服务）。
- 不能误认成已实现：sys_device=112 仅为 claimed，内核中不存在该符号；A1 三驱动
  仍为存量债，迁移未开始。
