# 0063：输入与编辑体验设计

2026-10-27。按用户要求，分别编写第一档现有行编辑与终端体验、第二档小型全屏终端
编辑器选型的设计；均为 P 类建议，未实施、未分配 ABI 或冻结第三方选型。

范围：`docs/plans/input_edit_foundation.md`、`docs/plans/terminal_editor.md`、
`docs/state.md` 与本记录。重新核对纪律、当前状态和宪法、显示/输入、UTF-8、POSIX、
Qt、CPython 与文件编辑源码；指出现有编辑器正文输入为 ASCII，避免误称已有 UTF-8 编辑。
文档区分字节保真、正常 sync、保存结果未知与掉电保证，及 Xshell 行编辑和真实 TTY。

验证：`python3 tests/docs_consistency.py --output-dir /tmp/xos_input_edit_docs_check`
通过（325 个本地链接、66 个 syscall、73 条历史来源）；
`python3 tests/abi_doc_consistency.py --output-dir /tmp/xos_input_edit_abi_check`
通过；`git diff --check` 通过。检查结果仅针对本文档组合，不改变旧客体资格。
未修改源码、SDK、报告或发行资产，未构建、未运行客体测试。下一步可由用户选择 F1/F2
开工；第二档先做候选和底座探针，不得把设计、宿主编译或既有资格当成客体验收。
