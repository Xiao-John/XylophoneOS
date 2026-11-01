# Host-path scrub attempt（未完成，已被取代）

状态：**NOT_COMPLETED / SUPERSEDED**，2026-11-01 登记。

本目录记录一次对冻结证据中作者主目录绝对路径（见 Issue #37）的全量字节
脱敏尝试。该尝试完成了内容改写的一部分（phase 1），未完成哈希级联与自校验
（phase 2/验证/清单均未落盘），随后被主动停止并**整体回滚**：

- 停止原因：同日主线合并的 [PR #56](https://github.com/Xiao-John/XylophoneOS/pull/56)
  以"恢复原始字节 + 入库守卫扫描器 + 环境模板"处理同一问题，出处保全且零级联；
  全量改字节路线与新立的
  [证据完整性契约](../../contracts/evidence_integrity.md)（git commit 唯一信任根、
  叶子互不哈希）方向相反。修改工作区字节也无法撤回已发布的 git 对象，隐私收益有限。
- 回滚证据：回滚后 `docs/` 内该路径前缀复现为回滚前计数；本目录工具保留为
  方法学存档（sink-first 拓扑级联、tar 成员字段、确定性重压、fail-stop 设计本身
  有参考价值），**未再执行，不代表通过任何验收**。
- 现行有效路径：Issue #37 线（PR #56 的扫描器与索引校验器）+
  `tests/report_manifest_check.py`（新报告目录的平铺根清单校验）。

本目录自身按证据完整性契约管理：`manifest.json` 平铺覆盖其余全部文件，
修改本目录任何文件时只允许同时更新该清单。
