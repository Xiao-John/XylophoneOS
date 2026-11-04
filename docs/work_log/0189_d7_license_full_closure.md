# 0189 D7 许可面收口（发版中止，回到本该完成的 D7）

2026-11-03 · 分支 `codex/d7_license_release_prep`（HEAD 起于 main `8b4dcee` = PR #66/#67 后）。

**缘起**：0188 完成"许可两叶"后启动了 0.0.2-1103 发版流程；用户裁定**发版中止**
（未打 tag、未传资产、未建 Release，已核实远端只有 1024/1026 两个 tag），回到 D7
把许可面真正收口——收口口径经用户确认为**许可面全闭**（QML/Quick 与 Qt 安全审查不在本轮）。

## 一、交付清单

| # | 项 | 产物 | 结果 |
|---|---|---|---|
| 1 | Qt 上游许可文本补全（缺口①） | `src/ports/qt6/licenses/LicenseRef-Qt-Commercial.txt`、`Qt-GPL-exception-1.0.txt`（从锁定源包原样提取，源包 sha256 与 `source_lock.json` 一致）；`licenses/components.json` QtBase 条目 notices 11→13、artifact_sha256 同步 | 已闭：`copy_notices()` 随包携带的文本从 29→31 份口径补齐 |
| 2 | LGPLv3 §4d0 对应源码与可重链接交付物（缺口②） | `src/ports/qt6/REDISTRIBUTION.md` + `redistribution_manifest.json`（义务→对应物映射、10 补丁/21 上游文件、48 项显式关闭特性、17 个静态库 1522 成员的路径+sha+成员数、重链接步骤、not_done 清单） | 已成文并机器可读；**资格仍 NOT_GRANTED**（打包核验未做） |
| 3 | 补丁修改显著标注（缺口③） | `src/ports/qt6/patches/MODIFICATIONS.md`（10 补丁逐条：上游文件/增删行数/目的/显著性判定/引入提交；+133/−86；显著 6、轻微 4；补丁头无 Date/Author → 如实 NOT_RUN，改用 `git log` 补引入信息） | 已闭（subagent 交付，含 0 处补丁内自带标注的实测结论） |
| 4 | GCC 运行库逐成员映射（GNU Seed O5/R2 残项） | `scripts/gcc_runtime_member_license_map.py` + `docs/reports/gcc_runtime_member_license_20261103/` | **397/407（97.5%）**：libgcc 140/147、libstdc++ 193/196、libsupc++ 64/64；类别 gcc_runtime_exception 314、gpl 23、other_copyright 55、no_declaration 5；10 个真歧义**如实未解析** |
| 5 | Qt 逐成员许可映射（NOT_RUN①⑧） | `scripts/qt_member_license_map.py` + `docs/reports/qt_member_license_20261103/` | （见第 2 节补记） |

### GCC 映射的解析方法（可复算）

五级递进：`dependency_file`(4) → `build_log`/`libtool 别名`(240+7，构建日志里的真实编译
命令行 + `ln -s` 全路径行) → `exact_stem`(82)/`stem_text_search`(12，目标架构过滤 + 实现
文件优先 + 按归档偏好 `libgcc/`/`libstdc++-v3/`) → `symbol_lookup`(52，`x86_64-elf-nm` +
`c++filt` 反查)。未解析 10 个的候选清单在 `findings.json` 的 `unmapped`，**不猜**。

## 二、Qt 逐成员映射（补记）

- 产物：`scripts/qt_member_license_map.py`（553 行）+ `docs/reports/qt_member_license_20261103/`
  （README、findings.json、manifest.json，`report_manifest_check` compliant）。
- **结果：1522/1522 解析、0 未映射、0 歧义**（widgets 10 个 `.a`/766 + widgets2 7 个 `.a`/756）。
- 解析层级：`object_record` **1522（100%）**——构建树保留了与归档成员**字节一致**的对象，
  其 `CMakeFiles/<Target>.dir/...` 路径镜像源码目录；集成者独立抽验 `qwidget.cpp.o`
  归档成员与构建对象 sha256 一致。生成源（moc/autogen）20 个已标注 `generated: true`。
- 声明类别：commercial_reference 1182、other_copyright 232、bsd_like 70、no_declaration 30、spdx 8。
- NOT_RUN ⑧ 答案：37 份上游文本对应表已产出，**12 命中 / 25 未命中（逐份注明原因）**；
  上一版 9/28 含 HPND 误报（许可文本词窗口搜索），agent 已整体移除该实现并更正；
  残留缺口（262 个仅版权/无声明成员的"成员→文本"方向覆盖）登记为
  `qt_license_text_member_coverage`（open）。
- 该叶前一版实现有缺陷（同名回退产生 42 个问题项），agent 迭代修复后改为全量
  `object_record`；过程见第七节。

## 三、机制补强（用户问"为何这么复杂/是否缺预先注册/能否不再重复付费"后追加）

诊断：复杂度不在许可判定（十几行正则），在**考古重建"成员→源"**——构建当时知道、
随后被丢弃的信息（GCC 依赖被清理、Qt 常规源码无 `.d`、日志残缺），三份脚本各造一套阶梯。
根因是两条**预先注册缺口**：①没有"归档成员来源"登记；②没有阻止"还有缺口却打印全绿"的闸门。

| 项 | 落地 | 效果 |
|---|---|---|
| **A 单一开放项登记处 + 闸门** | `licenses/open_items.json`（状态/证据/退出条件，8 项）；`scripts/license_audit.py` 从它派生 `not_completed` 并硬校验（证据缺失、状态非法、open 无退出条件、证据目录缺平铺 manifest → 直接失败） | 机制上杜绝"报告 NOT_RUN / 审计全绿"；本轮实测已拦下一次（Qt 报告缺 manifest 时 rc=1） |
| **B 归档成员来源契约** | `docs/contracts/archive_member_provenance.md`：下次重建起造归档必须同批产出 `member_manifest.json`（一手记录、禁推导冒充），逐成员审计改为读清单+校验器；**不追溯**既有归档（newlib/GCC/Qt 三份推导映射如实标注） | 下次同类审计 = 跑校验器，不再付考古成本 |
| **C 共享实现** | 登记为 `docs/tech_debt.md` **D12**：三份脚本抽成 `scripts/archive_member_map.py`，随契约首次重建落地 | 一次性还清三套阶梯的重复 |

## 四、登记更新

- `docs/licensing.md`：GNU Seed 段残余缺口改为"已交付（newlib 1053/1053、GCC 397/407）"；
  E16 段改为"逐成员映射/对应源码与重链接材料/补丁标注已交付，安全审查与打包核验仍 NOT_RUN"；
  Qt 节补收口小节（见第 4 节）。
- `docs/tech_debt.md`：D7 行更新为收口后的真实剩余（见第 5 节）。
- `docs/state.md`：许可行更新。
- `scripts/license_audit.py`：`not_completed` 从空列表改回**如实列出未闭合项**
  （这是 0188 的教训：把 `not_completed` 清空会让自动审计输出"全绿"，弱化了仍未取得的
  Qt 发行资格；本轮纠正）。

## 五、门禁（本地实测）

- `make smoke` **11/11**（build `6c9d67212c84d324`）：boot 6、kernel 18、task 12、
  process 13、file 8、persist 4、full_disk 1、libc 3、e08_storage 9、runtime 5、license-audit 7。
- `python3 scripts/build.py` BUILD_OK；`license_audit` PASS（新增 2 份 Qt 文本已进 SDK 许可副本）。
- `docs_consistency` passed（681 links / 71 syscalls / 73 history）；`abi_doc_consistency` PASS。
- `report_manifest_check` passed（新增报告全部 compliant）。
- 守门路径扫描（本轮全部改动文件）PUBLIC_READY、0 findings。

## 六、剩余缺口（诚实清单，未闭合就是未闭合）

| 项 | 状态 | 归属 |
|---|---|---|
| GCC 运行库 10/407 成员未解析 | 真歧义，见报告 `unmapped` | 继续挂在本行，直到有构建记录或人工裁定 |
| Qt 打包核验（随包清单与哈希复核） | NOT_RUN，发布时才能做 | 发版流程（发版已中止） |
| Qt 安全审查 | 范围外 | 另行跟踪（不属 D7 许可面） |
| Qt 商业许可核验 | N/A（仓库无商业授权材料） | 不可执行，非缺口 |
| QML/Quick | 未立项 | 功能线，不阻塞 |
| 字节级逐成员溯源 | NOT_RUN（抽查样本一致，未全量） | 两份映射报告均如实标注 |

## 七、过程记录（subagent 可靠性）

- 本轮 subagent 出现**批量故障段**：连续 8 次零产出（newlib 3 次 + Qt 映射 1 次 + 收口
  4 叶全部 null），期间改由主控直做（GCC 映射、Qt 文本、§4d0 材料）。
- 随后故障段过去：补丁标注叶与 Qt 映射重试均正常返回（补丁标注已交付）。
- 结论：subagent 可用但不保证；关键路径必须有主控可替代方案，交付以**落盘产物**为准、
  以返回文本为准要打折（多轮 null 返回但产物完整）。
