# 0188 D7 许可两叶与发版前小更改（README/版本/寄存器刷新）

2026-11-03 · 分支 `codex/ncursesw_w1`（基于 main `48882c9` = PR #66 合并后）。
用户口径：本轮完成 D7 的**许可两叶**（逐成员许可审计 + 静态分发审查）与 1–5 号小更改、
根 `README.md` 更新、版本定为 **0.0.2-1103**；**不发布**，完成后待命。QML/Quick 经确认
不在本轮范围（功能线，未立项）；D6（系统重建/自举）暂缓。

## 一、D7 许可两叶（并行 subagent 拆分执行）

| 叶 | 产物 | 结果 |
|---|---|---|
| newlib 逐成员许可映射 | `scripts/newlib_member_license_map.py`、`docs/reports/newlib_member_license_20261103/` | **1053/1053 成员全解、0 未映射、0 歧义**；类别 bsd_like 359 / other_copyright 317 / no_declaration 323 / spdx 54；1028 唯一源文件含 LGPL/GPL 者 0（独立正则复核，整树同正则可命中未编译端口 11 个 LGPL 文件证明抓取有效） |
| GNU Seed 分发审查 | `docs/reports/gnu_seed_distribution_20261103/` | 审查可结项：6 组件盘点 + 逐项分发判定 + 义务清单 O1–O10；**纠正前提**：Seed 已随 0.0.1-1024/1026 工作盘与 SDK 公开分发（本地字节与公开摘要 7/7 MATCH、FAT32 实测 170 项客体文件），义务已被触发且大部分履行 |
| Qt 静态分发审查 | `docs/reports/qt_static_distribution_20261103/` | 已满足 1 / 缺口 3 / 不适用 3 / **NOT_RUN 8**；Qt 二进制不随 0.0.2 分发，义务本版不触发；**未授予静态再分发资格** |

**执行方式**：4 个并行 subagent。Qt 叶与 components 叶正常交付；GNU Seed 叶落盘完整
但最终回话失败（返回 null），其产物经复核合格；newlib 叶**三次 subagent 尝试全部失败、
零产出**（首次被用户中止，后两次同样返回 null），改由主控直接实现——侦察数据先行
（AR 头解析、三棵构建树 `.Po` 交叉验证）后一次写成。

**发现并订正的错误**（诚实记录，均在本 PR 内修掉）：

1. GNU Seed 报告初稿的成员数错误：libgcc 144→**147**、libstdc++ 125→**196**、
   libsupc++ 49→**64**（GCC 侧 318→**407**）；newlib libc 199→**627**、libm 196→**426**
   （395→**1053**）。订正后在 README 与 `gnu_seed_inventory.json` 双处注明原值与订正依据。
2. **事实性登记冲突（R1）**：`docs/licensing.md` 称 Seed"没有公开发布"、
   `licenses/components.json` 5 条 `distribution_status: local_only`，均与已发布资产矛盾
   → 已按报告 2.1 节更正（sbase 的 `local_only` 属实，未改）。
3. `scripts/license_audit.py` 的两个 `not_completed` 已清空，改为以 `review_reports`
   引用三份报告 + `review_limits` 声明边界（不写死数字，避免腐化）；打印语句同步。
4. work_log 索引失真（见下）。components.json 的 defusedxml `modifications` QuickJS
   残留已改写为实际事实。

## 二、发版前小更改（1–5）

1. **`docs/state.md` 刷新**：宪法 v1.7、ABI **71** 已分配 syscall（`docs_consistency`
   实测）、`sys_device`=112 已登记+段 1a 合入（#64/#65）、ncursesw W1 终验合入（#66）、
   许可两叶、0.0.2-1103 定版待发；"下一步"改为发布准备 + 段 1b + D6/QML 未开工。
2. **`docs/tech_debt.md`**：C2/C3（PR #55 已合）、D2（PR #66 已合）移入"近期已清偿"；
   D7 改为"两叶本轮交付、剩余 QML/Quick 未立项"；D10 改为"0.0.2-1103 已定版未发布"。
3. **`docs/work_log/README.md` 索引补全**：补登记 0158–0167、0171–0173、0187、0188；
   重复编号按目录实测从 12 组更正为 **29 组**（0083/0085/0087/0090/0144–0149/0154–0157/
   0168–0170 漏登），并如实改正"自 0149 起全局唯一"的过时表述为"自 0188 起全局唯一"。
4. **`licenses/components.json` 卫生**：7 条 `source` 补固定版本/提交/直链
   （sbase 提交、idna/tzdata/psutil/Pillow/defusedxml wheel 直链），defusedxml
   `modifications` 改为实际事实；**95 条既有校验哈希逐条断言未变**。zlib 未改
   （其 URL 已绑锁定 sha256，改动反而与锁文件冲突）。遗留：FatFs、liteHTML 两条
   source 仍无版本固定（不在本轮清单），如实登记。
5. **D10 记账**：随版本定版更新（发布动作本身不在本轮）。

> 顺带：改 `components.json` 后 `license_audit` 曾因 SDK 副本哈希绑定旧文件而失败，
> 由单构建者重建后恢复 PASS——这是预期路径，不是回退。

## 三、smoke 三项失败的处置（本轮追加，经用户裁决）

**现象**：`make smoke` 在 `task` 确定性失败；单独复跑另发现 `process`、`libc` 同因失败
（8 过 3 挂：boot/kernel/file/persist/full_disk/e08_storage/runtime/license-audit 过）。

**根因（已定位、已复现、与本轮改动无关）**：`d6363f8`（2026-10-27，xypm P2 合入）
给 supervisor 加了 fail-closed 持久化恢复门——注释明确"只有确定 not_found 才放行"。
这三个测试**不挂工作盘**启动 → files 客户端 `init()` 后 `stat` 返回 `io(-7)`
（串口可见 `[files] bootstrap-stat error=-7`）→ 门常开 → `demo keep` 被
`maintenance: persistent recovery required; command blocked` 拒绝。对照实验：给同一次启动
挂上工作盘，门不再出现。`boot`/`kernel`/`libc` 之外的其余 smoke 本就挂盘，故不受影响。

**本轮改动不可能是成因**：diff 只含文档、`VERSION`、`scripts/license_audit.py`、
新增映射脚本与报告；内核代码零改动（banner 的 `XOS 0.0.2` 是 `src/kernel/core/console.cpp`
硬编码，与旧 `VERSION=0.0.1-1026` 本就不一致，本轮正好对齐）。

**处置（用户选"本轮修测试"）**：
- `tests/task_smoke.py`、`tests/process_smoke.py`、`tests/libc_smoke.py` 各补一个临时
  16 MiB 工作盘（`make_work_disk.make_image()`，与仓内其余 40+ 个磁盘测试同一写法），
  在 `finally` 里清理；每处都留注释说明恢复门语义，避免后人删盘。
- **登记 D11**：无盘启动下恢复门常开属设计语义问题，"io 是否应视为无标记"留给宪法原则
  裁决，本轮不改门（不削弱 fail-closed）。

## 四、README 与版本

- 根 `README.md`：补"下一版本 0.0.2-1103 已定版未发布"说明；修正 Qt 过时表述
  （"Qt 尚未实现"→ 静态受限客体验收、QML/Quick 未实现）。
- `VERSION`：`0.0.1-1026` → `0.0.2-1103`（`make build` 的 manifest 与 install ISO 随之携带）。
- `docs/releases/next_release.md`：记录版本号已定、冻结/打包/上传未执行。
- 登记同步：`docs/licensing.md`（GNU Seed 段事实更正、表 2 行、newlib 映射段、Qt 静态
  分发新节、第 6 节规则改为"已分发"）、`docs/e06_libc.md`、`docs/e08.md`。

## 五、门禁（本地实测，最终）

- `make smoke`：**11/11 全过**，build `643d9048eb759596`——boot 6、kernel 18、task 12、
  process 13、file 8、persist 4、full_disk 1、libc 3、e08_storage 9、runtime 5、
  license-audit 7 份材料 PASS（含第三节的三项测试修复）。
- `python3 scripts/build.py`：**BUILD_OK**（kernel 512080 字节，manifest `version=0.0.2-1103`）。
- `tests/docs_consistency.py`：**passed**（local_links 679、allocated_syscalls 71、
  history_sources 73）。
- `tests/abi_doc_consistency.py`：**PASS**。
- `tests/report_manifest_check.py`：**passed**，新增三份报告均在 `compliant` 列表
  （`newlib_member_license_20261103`、`gnu_seed_distribution_20261103`、
  `qt_static_distribution_20261103`）。
- `tests/check_public_evidence_paths.py`（本 PR 全部 24 个改动/新增文件）：
  **PUBLIC_READY，findings 0**。
- `licenses/components.json` JSON 合法（33 组件）；`make license-audit` 报告
  `not_completed: []`、`review_reports` 指向三份审查报告。

## 六、边界

- 未发布任何 Release，未打 tag，未上传资产；1026 仍是唯一可下载发行。
- 三份报告都是**映射 / 材料与流水线审查 / 义务清单**，**不是法律意见**；材料检查通过
  不等于法律兼容性认证。Qt 静态再分发资格**未授予**；字节级逐成员溯源 NOT_RUN。
- QML/Quick 移植、D6 系统重建/自举、SMP、绝对峰值仍未完成，见 `docs/tech_debt.md`。
