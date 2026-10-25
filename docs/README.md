# XOS 文档索引

2026-10-25。过程文档已合并；默认只读这些入口，不再为每个阶段保留散页。

## 先读

1. [开发纪律](Discipline.md)
2. [当前状态](state.md)
3. [总体计划](xos_plan.md)
4. [已定决策](decisions.md)

## 当前实现

- [架构、启动与异常/内存边界](architecture_and_boot.md)
- [实模式练习](real_mode_boot.md)
- [E04 用户态装载/SDK](e04_loader_sdk.md)
- [E05 文件服务](e05_file_service.md)
- [E06 libc/newlib](e06_libc.md)
- [E07 持久工作盘](e07_persistent_work_disk.md)
- [工具链与构建](toolchain.md)
- [受限 C++ 子集](cpp_subset.md)
- [命令使用手册](usage/index.md)
- [给朋友的用户程序快速开始](friend_user_program_quickstart.md)
- [CPython 3.14.9 PY0 移植](../src/ports/cpython/README.md)（[工作记录](work_log/0030_cpython_py0.md)）

## 历史与验收

- [E01–E07 简史](history/e01_e07.md)
- [E08 原生工具链总览与结论](e08.md)
- [0.0.1 发布说明](releases/0.0.1-1024.md)

## 正在进行/后续

- [dash/shell 移植侦察](shell_port_scout.md)
- [独立应用与包管理](package_management.md)（P0已验，P1–P3待实施）
- [公共线程契约与E13-T计划](threading_contract.md)
- [UTF-8文本接口计划](utf8_text_plan.md)（U0/U1已通过）
- [Open Adventure依赖内建计划](adventure_port_plan.md)
- [CPython移植计划](cpython_port_plan.md)
- [Qt 移植评估](qt_port_assessment.md)
- [许可管理](licensing.md)

## 约定

- E01–E07 的逐阶段 work log、E08 的 plan/prompt/handoff/report 已合并到上述两篇
  简史；旧文件不再恢复。
- 构建证据仍在 `build/`、私有 `.cache/xos_seed/` 和 git 历史中；文档只给入口和
  结论，不复制大段日志。
- `AGENTS.md` 仍是 agent 入口；本索引不替代 `state.md` 的当前事实。
