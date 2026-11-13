# 历史证据宿主路径规范化（2026-11-13）

公共证据检查（`tests/check_public_evidence_paths.py`）在历史报告中发现了宿主私有路径。
本次用 `scripts/normalize_public_evidence.py` 做**仅路径**替换：

- `/Users/…`、`/home/…`、`/private/tmp/…`、`/var/folders/…`、`/opt/homebrew/…`、
  `/Library/Frameworks/…`、`/workspace/scratch/…`、`/opt/codex/runtimes/…`、
  `C:\Users\…` → `${XOS_LOCAL_PATH}`；
- 工具会在写入前比对文件内所有 40–64 位十六进制串，拒绝任何会改变散列的重写；
- 命令、状态、结果字段除路径占位符外保持原样；原始宿主日志不随仓库分发。

本次涉及 7 个文件：`dash_c2_20261026/{dash_c2_final_report,dash_c2_oom_report}.json`、
`dash_c3_20261026/{dash_c2_report,dash_c3_report,dash_c3_report.raw}.json`、
`qt_e15_qualified_20261028/qualified-dash-{c2,c3}.json`。

## 未处理（需要策略决定）

1. **容器/客体路径**：`/out/…`、`/src/…`、`/tests/…` 被扫描器归类为
   `absolute_command`（348 处）。它们是 dash/Qt 测试容器的稳定挂载路径，不是宿主私有路径；
   改写会破坏证据可读性。
2. **上游归档内的字符串**：`src/ports/aurora_browser/upstream/litehtml-0.9.tar.gz`
   内含 `/home/…` 与 `file://…`（各 2 处）。重新打包会改变 `source_lock.json` 的固定哈希，
   不在路径清洗范围。

建议对 (1) 在扫描器中把容器挂载根加入允许前缀，或对 (2) 明确“上游归档按固定哈希豁免”。
