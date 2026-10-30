# XOS文档入口

按职责读一份权威说明，状态与原则分开。当前主线和阶段证据见[state](state.md)。

## 开始工作

1. [开发纪律](Discipline.md)：流程、文件边界、证据和PR交付。
2. [当前状态/占用](state.md)：实际能力、冻结证据与接续任务。
3. [项目宪法](xos_plan.md)：第一部分裁定设计，第二部分登记事实。
4. [ABI登记](contracts/abi_registry.md)及对应专项契约；[决策入口](decisions.md)不再重复规则。

## 目录与权威位置

| 位置 | 用途 | 维护方式 |
|---|---|---|
| 根入口 | 宪法、状态、流程、SDK/架构/工具链及使用入口 | 稳定路径，避免重复登记 |
| contracts/ | ABI分配、线程、POSIX子集、Qt协作 | 细化原则内的接口；分配与验收分开 |
| implementation/ | 已实现的显示、线程、Shell、Make | 当前行为、错误/资源边界与证据入口 |
| plans/ | 包/CPython/Qt/POSIX/ISO/UTF-8/游戏/工具后续 | 已实现与建议/未验显式区分 |
| history/ | 合并后的实现/证据摘要与source_index.json | 原文按Git提交/路径/哈希恢复，不复制过程叙事 |
| work_log/ | 尚未合并的新任务交接 | 收口后归入主题history，保留来源映射 |
| reports/、releases/ | 冻结测试、失败、来源和发行回执 | 不因重组移动或改写 |
| usage/ | 用户命令手册 | 面向使用，保留现有路径 |

## 按任务阅读

- 基底：[架构/启动](architecture_and_boot.md)、[C++子集](cpp_subset.md)、[工具链](toolchain.md)、
  [用户装载/SDK](e04_loader_sdk.md)、[文件服务](e05_file_service.md)、[libc](e06_libc.md)、[持久盘](e07_persistent_work_disk.md)。
- 移植：[线程契约](contracts/threading.md)、[Qt协作](contracts/qt_platform.md)、[POSIX](contracts/posix_subset.md)、
  [QtCore](implementation/qt_core.md)、[显示](implementation/display.md)、[Shell](implementation/shell.md)、[Make](implementation/make.md)。
- [日常工具集设计](plans/daily_utilities.md)：DU1/2首批13命令已有实现与定向证据；完整逐命令资格、后续工具及包/ISO交付见state。
- 独立扩展：[应用故障包计划](plans/app_fault_bundle.md)的[FB0格式与勘查](implementation/fb0_fault_bundle_contract.md)
  已按限定范围完成；[FB1/FB2 使用与边界](implementation/fb12_fault_bundle.md)已在本地实现并验证。[音频输出](plans/audio_output.md)仍仅为计划。
  两项不新增ABI或改变既有主线排期。
- 下一阶段：[包管理](plans/packages.md)、[CPython](plans/cpython.md)/[扩展](plans/cpython_extensions.md)、
  [Qt](plans/qt.md)、[POSIX路线](plans/posix.md)、[工具菜单](plans/userland.md)、[UTF-8](plans/utf8.md)、
  [ISO](plans/iso.md)、[Open Adventure](plans/adventure.md)。
- 使用/分发：[开发快速开始](friend_user_program_quickstart.md)、[命令](usage/index.md)、[许可](licensing.md)、
  [下一发行](releases/next_release.md)、[验收登记](acceptance.md)。
- 历史：[E01–E07](history/e01_e07.md)、[E08](e08.md)、[Shell](history/shell.md)、[线程](history/threading.md)、
  [用户态](history/userland.md)、[包](history/packages.md)、[引导/显示](history/boot_display.md)、
  [发行/审计](history/delivery_audit.md)、[设计沿革](history/design.md)。

冻结报告里的旧文件路径、旧编号和源码哈希保留原样，只描述其原输入。压缩不重跑旧测试，
也不丢弃失败；迁移关系和原文摘要见[来源索引](history/source_index.json)。
