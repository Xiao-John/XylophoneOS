# XOSBND1 启动载荷容器契约（v1）

2026-11-05。状态：**字节布局冻结（DU4 前期）**；尚未生成发行 ISO、未做客体安装验收。
对应设计见 [DU4 计划](../plans/daily_utilities_iso_payload.md)。本契约只约束
宿主生成器与用户态解析；**固件/loader/内核不解析容器**，继续把 ISO 根 `DASH.ELF`
当不透明字节经 `sys_boot_payload` 交付。

## 1. 目标与非目标

- **目标**：在单一 ISO 载荷文件中携带 dash ELF + bootstrap xypm XPK + 日常工具 XPK
  等有界成员，供用户态 supervisor 校验后分别安装/启动。
- **非目标**：签名与发布者身份（摘要只检损坏）；内核内包解析；绕过 P2 维护门禁的
  授权；自动升级旧 dash ISO；改变 `sys_boot_payload` ABI。

## 2. 字节布局（全部小端）

### 2.1 头（固定 64 字节）

| 偏移 | 宽度 | 字段 | 约束 |
|---:|---:|---|---|
| 0 | 8 | `magic` | ASCII `XOSBND1` + `NUL`（`58 4f 53 42 4e 44 31 00`） |
| 8 | 4 | `version` | `u32` = **1**；未知版本拒绝 |
| 12 | 4 | `member_count` | `u32`，**1..16**（首版） |
| 16 | 8 | `total_bytes` | `u64`，等于容器文件总长；`≤ 33554432`（32 MiB，`iso_payload_max_bytes`） |
| 24 | 4 | `names_bytes` | `u32`，名称区字节数；`≤ 2048` |
| 28 | 4 | `reserved0` | 必须为 0 |
| 32 | 16 | `reserved1` | 16 字节，必须全 0 |
| 48 | 16 | `reserved2` | 16 字节，必须全 0 |

### 2.2 成员表（每项固定 64 字节，紧跟头）

| 偏移（项内） | 宽度 | 字段 | 约束 |
|---:|---:|---|---|
| 0 | 4 | `type` | `u32`，见 §3；未知类型拒绝 |
| 4 | 4 | `name_off` | `u32`，相对名称区起点；`name_off + name_len ≤ names_bytes` |
| 8 | 4 | `name_len` | `u32`，`1..127` |
| 12 | 4 | `reserved` | 必须为 0 |
| 16 | 8 | `data_off` | `u64`，相对**容器起点** |
| 24 | 8 | `data_len` | `u64`，`≥ 1` |
| 32 | 32 | `sha256` | 数据区 32 字节 SHA-256 |

布局顺序：`header(64) | entries(64*count) | names(names_bytes) | data…`。
名称区与数据区之间可有 0–3 字节填充使 `data_off` **4 字节对齐**；填充必须为 0。

### 2.3 名称区

- 紧凑拼接的 UTF-8 名称，无 NUL、无 `/`、无控制字符、ASCII 可打印（`0x20..0x7e`）。
- 同一容器内名称唯一；名称只用于诊断与安装目标提示，**不构成授权**。

### 2.4 数据区

- 各成员 `[data_off, data_off+data_len)` **互不重叠**，且完全落在
  `[names_end_aligned, total_bytes)` 内。
- 成员按 `data_off` 升序排列（生成器保证；解析器校验无重叠即可不要求顺序）。
- 间隙填充为 0。

## 3. 成员类型（首版冻结）

| type | 名称 | 数量 | 内容 |
|---:|---|---|---|
| 1 | `dash_elf` | **恰好 1** | 合法 ELF64（`0x7fELF`），作 `/usr/bin/dash` 候选 |
| 2 | `bootstrap_xypm` | 0..1 | 合法 `.xpk`（ustar 子集，见 packages.md P0 v1） |
| 3 | `daily_tools_xpk` | 0..1 | 合法 `.xpk` |
| 4 | `auxiliary_xpk` | 0..N | 合法 `.xpk`；首版允许但生成器默认不产出 |

- `type=1` 缺失、或 `type∈{2,3}` 重复出现 → 拒绝。
- 数据魔数校验：type1 前 4 字节 `7f 45 4c 46`；type≥2 前 5 字节 `ustar` 出现在
  偏移 257 的 ustar 标志（或按 xpk v1 规则校验 tar header checksum）。
  校验失败 → 拒绝，**不得**把整个容器当 dash 执行。

## 4. 解析器必须拒绝

未知 `version`/`type`；`member_count`/`names_bytes`/`total_bytes` 越界或溢出；
头/表/名称/数据越界；成员区重叠或与头表重叠；名称非法或重复；`reserved≠0`；
SHA-256 不符；type1 非 ELF；type≥2 非 xpk；`dash_elf` 数量 ≠1；
`bootstrap_xypm`/`daily_tools_xpk` 重复。拒绝时不得部分安装、不得回退执行容器字节。

## 5. 与现有机制的关系

| 机制 | 关系 |
|---|---|
| `sys_boot_payload(off, buf, len)` | 仍按不透明字节分块拷贝；容器总长 ≤ 32 MiB 预算 |
| `install_boot_dash()`（file_ui） | **必须先识别 magic**：是容器则拒绝写入 `/usr/bin/dash`（安装路径 DU4 后续实现）；非容器 ELF 走旧路径 |
| `spawn_buffer` 128 KiB | 不用于装整容器；成员落盘后用 `spawn_file`/流式装载（已支持） |
| P2 xypm 安装 | 容器只负责**运送**；安装仍走 P2 门禁/租约/journal |

## 6. 实测基线（2026-11-05）

| 项 | 值 |
|---|---|
| `image_buffer`/`spawn_buffer` | 131072（128 KiB） |
| `iso_payload_max_bytes` | 33554432（32 MiB） |
| dash.runtime | 277064 |
| xypm.xpk | 1382400 |
| daily_utils.xpk | 11458560 |
| idna.xpk | 368640 |
| 合计（候选组合） | ≈ 12.9 MiB ≪ 32 MiB（含容器头/表余量充足） |

## 7. 边界

- 本契约为工程冻结，不是安全证明；摘要不提供 authenticity。
- 生成器与解析器的往返/畸形测试是前期交付；空盘安装、重启复用、失败恢复、
  真实 P2 安装矩阵属 DU4 正文，未完成前不声称 ISO 安装可用。
