# 0077：全部本地工作与远端 main 整合

2026-10-28。用户明确要求同步全部远端改动、统一冲突并直接 push；本次允许直接
更新 main，后续开发仍按既有 PR 纪律，不据此建立永久直推例外。

## 输入与保存

远端 main 为 be1e9c1：PR #9 QtGui/QPA、#10 输入编辑/文档、#11 xypm P2 均已合并。
本地从 codex/ncursesw_w1 的 025e52c 开始，已含 792e5e2 的日常工具/UTF-8/游戏/P2
组合与 ncursesw 设计。四个登记工作区已检查，其他三个干净；当前七项未提交契约/脚本/
探针保存为 6403fb9。同步期间新增的 probe_utf8_link.py 与宽字符探针补充也一并保存，
不将其视为客体验收。没有修改或清理 localpilot、build/cache 或其他工作区文件。

## 冲突与文档

六处冲突逐项处理：qt_platform 保留最新合入状态；multilingual 保留实际 UTF-8 路径
实现与资格；packages 保留远端对 P2 限定验收的准确表述；terminal_editor 保留用户
已调整的 ncursesw/nano 方向；state 合并 Qt G04、工具集、P2 与 ncursesw 实际进度，
移除重复/过期段落。xsh_line_edit_smoke 的两条中文路径预期保留本地已验证的 not found，
不退回旧 ASCII 路径实现的 cannot read program。无手工生产运行时代码冲突修复。

宪法 C20–C26 和原作者提交保留；DU 登记及入口修正为已有实现/定向证据，DU3/4和
完整资格仍未完成。Qt 原冻结报告及发布资产不改写，Qt G04 只在其原输入下通过；
本次整合不冒充包含日常工具、输入编辑与新探针的新组合客体资格。

## 检查与接续

文档检查通过（404链接、66 syscall、73历史来源），ABI表12项通过；
许可材料核对62处notice引用及81项精确哈希，Python探针语法通过。执行合并标记与差异检查，
以及新增 Python 探针语法检查。核对本地与远端的源码文件均保留：原本只存在一侧的
文件不得遗漏，双方共同源码内容相同则保持原样；唯一测试预期冲突按上述行为裁决。
源码保全核对52个单侧文件、676个相同共享文件、19个差异文件按父版本/新增探针保留；
摘要存于 /tmp/xos_full_sync_checks/source_materials.json。
license_audit.py 首次指向该临时检查目录，因没有 sdk/manifest.json 失败；未制造SDK回执
补过。随后仅核对真实源码许可材料；未重建匹配SDK，SDK声明副本审计明确为未运行。

本轮未重建系统/SDK/Qt、未执行 ncursesw 客体或重复旧压力/功能测试。现有验收和
built_unverified、partial、NOT_RUN 状态保持。后续 W0/W1 继续冻结真实终端和多字节
依赖，完成实现并提交后再验收；完整工具发行/空盘ISO与Qt Widgets/QML分别推进。
推送采用普通快进更新，若远端移动则重新整合，不 force push；最终远端 SHA 现场核对。
