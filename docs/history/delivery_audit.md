# 发行、审计与整合：实现摘要

截至2026-10-27。当前状态见[state](../state.md)，本页保留可复核实现与证据。

## 发行与审计

- 0.0.1-1024首个纪念发行；0.0.1-1026已发布，tag/source db5b46c，build7a4668477d7323de。
  release smoke11/11、7份许可材料，SDK/source/images完整摘要见[发行回执](../releases/release_0_0_1_1026.json)。
- audit_report_01 A01：files恢复区分明确缺失与I/O失败，预检材料、检查close/rename/unlink/
  sync，journal延后删除；最终delete flush失败尽力恢复marker但仍失败关闭。正常replace先验
  目标/身份，保留失败材料；不保证持续坏盘或任意掉电可恢复。
- A02/A03：维护ABI改62/23–24，当前表与源码核对，旧冻结编号不替换；过期状态修正。
- A04：发行按系统manifest核SDK完整集合/目录/摘要、ABI/配置/build，固定C++运行库来源，
  验证实际拷贝与成品绑定；拒绝旧staging。不因此断言已发1026错配。

0054独立build e78fbff3985357f3，kernel385084字节，镜像SHA256
44f1551140474c60bbe6478604a379e6e8fc9d4106de48e910c0c9b0295a80bf。
21项真实FatFs宿主故障/对照、客体恢复5项、维护9项、SDK绑定11项、当时ABI表8项及许可7份
通过；资源[130337,2,0]。build/audit_01/final_receipt.json绑定源码/SDK/报告；旧失败不覆盖。

## PR #3/#4与本地兼容

- PR #3原头f84745a对5b4e5e1可合并，但与本地熵63/墙钟64发生分发语义冲突，且有5文本冲突。
  三方保留审计/CPython、SDK配置字段、RDRAND/VGA/RTC；显示改65/66，旧报告原样。
- 0059最终build76a2e4380f64fb2e、kernel430140字节、xos.img SHA256
  a6554ffbad566a12f6645b4b259e64c94c41b50123e1b7a1be6de0ffba374ed6。
  新组合7组（3启动、显示23检查/线程/权限/回收、既有CPython熵/墙钟、有/无RDRAND）、
  ABI表12项/编号唯一性、boot_info宿主、SDK绑定11项、许可7份通过。
- 首次probe已输出正确结果，测试未开trace而误等退出标记；修fixture后重建/重验。失败日志在
  build/pr_3_compat/failed_attempt_1；最终receipt与源544项/产物绑定，未改成全G02或全PY3重验。
- PR #3 squash afcfe47与原PR tree一致；备份cb26f7b后mixed对齐，906工作文件哈希无变化。
  交付PR #4（91a0c71）已合入a265061，原显示主体不重复提交；后续用独立分支/PR。

## 未运行项

无新全量压力、掉电/扇区撕裂、完整线程C++ SDK/完整CPython B2–B4再验或新公开发行资格。
POSIX契约PX0仅文档，Qt和完整POSIX未实现；xypm P2-2 guest尚未通过。

## 合并来源

原文按[source_index.json](source_index.json)记录的提交、路径和SHA256恢复；以下锚点保留旧引用。

<a id="log-0023_first_release"></a>
- `docs/history/delivery_audit.md#log-0023_first_release`
<a id="log-0039_a2_attempt"></a>
- `docs/history/delivery_audit.md#log-0039_a2_attempt`
<a id="log-0045_release_prep"></a>
- `docs/history/delivery_audit.md#log-0045_release_prep`
<a id="log-0049_commit_snapshot"></a>
- `docs/history/delivery_audit.md#log-0049_commit_snapshot`
<a id="log-0050_release_candidate"></a>
- `docs/history/delivery_audit.md#log-0050_release_candidate`
<a id="log-0053_audit_snapshot"></a>
- `docs/history/delivery_audit.md#log-0053_audit_snapshot`
<a id="log-0054_audit_01_fixes"></a>
- `docs/history/delivery_audit.md#log-0054_audit_01_fixes`
<a id="log-0056_posix_subset_contract"></a>
- `docs/history/delivery_audit.md#log-0056_posix_subset_contract`
<a id="log-0057_pr_3_conflict_review"></a>
- `docs/history/delivery_audit.md#log-0057_pr_3_conflict_review`
<a id="log-0059_pr_3_local_compat"></a>
- `docs/history/delivery_audit.md#log-0059_pr_3_local_compat`
<a id="log-0060_pr_3_squash_alignment"></a>
- `docs/history/delivery_audit.md#log-0060_pr_3_squash_alignment`
<a id="source-state_cb26f7b"></a>
- `docs/history/delivery_audit.md#source-state_cb26f7b`
