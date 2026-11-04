# 0201 — Qt 262 成员文本覆盖核对

2026-11-04。分支 `codex/qt_text_coverage`（基于 main `fdab2806`）。
清偿 `licenses/open_items.json` 的 `qt_license_text_member_coverage`
（退出条件：262 成员按类别完成『成员→上游文本』覆盖核对并记录，或证明条款由
COPYING/SPDX 表达式整体覆盖）。

## 1. 范围与方法

`other_copyright` 232 + `no_declaration` 30 = **262**（`findings.json` object_record
tier 成员，已带 `component_license_ids`）。覆盖记录
`docs/reports/qt_member_license_20261103/text_coverage.json`：

- **242 个**按 `component_license_ids` → Qt `LICENSES/<id>.txt`
  （freetype FTL / GPL-2.0-only、harfbuzz MIT、zlib Zlib、
  pcre2 LicenseRef-BSD-3-Clause-with-PCRE2-Binary-Like-Packages-Exception）；
  文本 sha256 自锁定 `qtbase-6.8.3-gui/LICENSES` 钉定。
- **20 个** AUTOMOC/RCC 生成件（`mocs_compilation.cpp.o`、`qrc_example_icons.cpp.o`
  等，`findings.totals.generated_sources`=20）无组件 ID：按 Qt 组件 SPDX 表达式
  `LicenseRef-Qt-Commercial OR LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`
  对应四份 LICENSES 文本**整体覆盖**（退出条件第二路径）。

## 2. 结果

**262/262 covered，uncovered 0。** 覆盖方法计数：
`component_attribution_to_LICENSES_text` 242、
`generated_by_moc_rcc_inherits_qt_component_spdx_expression` 20。

**边界**：本记录是工程覆盖核对，**不是再分发资格**——Qt 静态再分发资格仍
NOT_GRANTED，待 `qt_static_redistribution_packaging_verification` 与
`qt_static_redistribution_security_review` 两个 deferred 关口（发版步骤 B）。
非法务意见。

## 3. 登记

- `text_coverage.json` + README 节 + 目录 `manifest.json` 重生成（3 文件）。
- `open_items.json`：`qt_license_text_member_coverage` → `not_applicable`。
- work_log README 索引 0201。

## 4. 验证

```text
python3 tests/report_manifest_check.py   # passed
python3 tests/docs_consistency.py        # passed
python3 tests/check_public_evidence_paths.py --commit HEAD --base origin/main
# text_coverage.json 内 sha256 与 LICENSES 源文件一致（生成时校验）
```
