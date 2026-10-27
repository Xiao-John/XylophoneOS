# 0064：多语言设计与输入编辑第一档

2026-10-27。用户提高 UTF-8 输入与文件优先级，要求单列多语言设计并直接开始第一档。
[多语言路线](../plans/multilingual.md)将正文输入/内容保真列为 M1，UTF-8 路径为紧接的
M2；FatFs 现为 ASCII 路径，中文文件名仍未实现。更新第一档、第二档设计和 edit 帮助。

F1 由 editor agent 在 `src/user/services/file_ui.cpp`、`tests/editor_f1_smoke.py` 实现：
UTF-8 正文输入、逐字节文档、按行显示/插入/替换/删除、`::`、脏缓冲保护和安全显示。
F2 由 xsh agent 在 `src/user/programs/supervisor.cpp`、`tests/xsh_line_edit_smoke.py`
实现：左右/Home/End/Delete、行内插入删除、16 条内存历史和草稿、有限 ANSI 序列及
UTF-8 码点输入。主 agent 负责共享文档、最终构建与检查。未改 dash 或分配 ABI。

## 构建与证据

- Python 3.12.15，QEMU 11.1.2，pc-i440fx-10.0、qemu64、TCG、单核、512 MiB。
- `python3 scripts/build.py --output-dir build/input_edit_final` 通过，build `3200de2c3b80a9d9`，
  `xos.img` SHA256 `4f6e91523531fd1070694063ccbaccfa5b884a806a9aa99e16db43e1bd60c2f1`。
- `python3 tests/editor_f1_smoke.py --image build/input_edit_final/xos.img --manifest build/input_edit_final/manifest.json --report build/input_edit_final/editor_report.json`：通过，
  验证控制/非法字节安全显示、中文输入及行编辑、非法输入/脏保护、sync 后宿主读取文件逐字节相符。
- `python3 tests/xsh_line_edit_smoke.py --image build/input_edit_final/xos.img --report build/input_edit_final/xsh_report.json`：11 项通过，包括中文光标、历史草稿、非法输入、CRLF 和序列超时。
- `python3 tests/utf8_text_smoke.py --image build/input_edit_final/xos.img --report build/input_edit_final/utf8_report.json`：6 项通过；该旧脚本报告的 build_id 来自默认 manifest，
  与本次不对应，按报告中的镜像 SHA256 与上方 manifest 绑定，不采用其 build_id。
- `python3 tests/xsh_ui_smoke.py --system-dir build/input_edit_final --output-dir build/input_edit_final/xsh_ui`：11 项通过。
- `python3 scripts/license_audit.py --build build/input_edit_final`：7 份材料通过，逐成员审计未完成。
- `python3 tests/docs_consistency.py --output-dir /tmp/xos_multilingual_docs_check`、
  `python3 tests/abi_doc_consistency.py --output-dir /tmp/xos_multilingual_abi_check` 与
  `git diff --check`：通过。

先前构建 `2c517ff4b33c694e` 期间 supervisor 源码又有更新；其结果不作为最终组合资格。
首次 Xshell 测试对实际错误路径的预期不符，修正测试预期后在最终组合通过。

## 限制和接续

第一档整体 **partial**：尚未对 8192/159 边界的完整组合、满盘/服务故障/结果未知、客体
sync 后重启、完整历史淘汰、前台 Escape 与后台输入竞争、换行重绘/异步输出做专项验收。
测试中的正常 sync 后是从宿主读取私有盘，并非客体重启。终端刷新使用有限 VT 单行模型；
组合字、emoji 宽度和字素簇不保证。历史仅保存在内存；文件冲突和任意掉电安全未承诺。
旧 `utf8_text_smoke` 的报告标识偏差保留说明，不修改旧报告；未来可修脚本绑定 manifest。

下一步优先补齐上述第一档验证，并按 M2 先冻结 UTF-8 路径、FatFs 转换与对象身份的
一致性契约，再开展独立实现和专盘验收。无源码/文档/build 占用。
