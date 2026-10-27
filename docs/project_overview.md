# XOS 项目总览

2026-10-26。本页给新读者和 release 准备一个当前视图；细节以 `state.md`、
`xos_plan.md`、work log 和报告为准。

## 这是什么

XOS Revival 是一个 x86-64、BIOS 启动的独立操作系统项目：NASM + 受限 C++
微内核、用户态 supervisor/files、FAT 工作盘、原生 GCC/G++ 工具链和可选的
dash/xsh。目标是能自己开发、保存、编译和运行程序，不以商业产品、论文或
替代 Linux 为成功前提。

当前主线构建为 BIOS/QEMU（`xos.img` / file-backed ISO）；UEFI 尚未实现。
`localpilot/` 是独立项目，不属于 XOS 构建、扫描或清理范围。

## 当前已交付

- 启动、长模式、异常/内存、任务/进程隔离、supervisor 与 files 服务。
- FAT32 持久工作盘；文件编辑、目录、同步、重启保留。
- 原生 SDK/GCC/G++/Binutils 和客体 C/C++ 编译运行。
- xsh 原生入口；dash 0.5.13.5 的 B0–B2及PR #2 C1–C3受限gate；流水线/隔离/HereDoc/exec/Make已有各自证据。
- file-backed El Torito ISO：`KERNEL.BIN` 从 ISO 读入，dash 作为 payload
  自动安装；0047解除旧容量限制，kernel文件8 MiB/内存16 MiB、payload32 MiB。
- CPython 3.14.9 PY0/PY1 与 T3-PY 真实 pthread/GIL gate。
- xypm P0/P1和P2-1门控已验；P2-2客体包校验/只读计划已实现初版并成功构建，
  尚未guest验收；P2-3持久恢复、P2-4写命令和P3仓库未完成。
- Open Adventure 在 XOS 内构建的受限验证；完整游戏/文本门未收口。

## 当前证据

- 0.0.1-1026已发布，tag/source为db5b46c，build7a4668477d7323de；release smoke
  11/11与7份许可材料检查，资产/SDK/source哈希见[发布回执](releases/release_0_0_1_1026.json)。
- 线程T0–T2、T3-PY与dash B/C各自冻结资格保留在对应reports/work_log，不改绑本地后续源码。
- 0052系统熵候选build46cb97b1555633f1已有RDRAND/不支持两种配置证据；未更新1026资产。
- xypm P2-2仍只有实现/构建，guest与畸形输入未验。0054针对审计错误另建隔离回执，
  以[当前状态](state.md)和[0054](work_log/0054_audit_01_fixes.md)为准，不构成新release。

## 明确未完成

- CPython T3-QT、SMP、完整POSIX、信号/终端语义；受限阻塞pipe已由PR #2交付。
- xypm P2-2 guest/adversarial验收、P2-3持久日志/启动恢复、P2-4客体写命令、P3签名仓库；dash完整POSIX。
- Qt实现、UEFI及发行签名。0.0.1-1026打包/发布已完成，后续源码另验。
- 长时间/随机压力、旧全量回归未重跑；不得写成全绿。

## 文档与压缩材料

- 入口：`README.md`、`docs/README.md`、`state.md`、`xos_plan.md`、
  `decisions.md`。
- `work_log/` 保留过程证据，不逐篇当入口；`docs/history/` 是历史简史。
- `docs/reports/threading_20261025/` 是冻结的线程资格材料，含失败 attempt
  日志，不能删成“全绿”摘要。
- 压缩包：`src/ports/dash/upstream/dash-0.5.13.5.tar.gz` 是离线构建必需；
  `build/releases/0.0.1-1024/*.tar.gz` 是旧发行附件/源码材料，不是文档。
  新 release 应重新生成并登记哈希，不复用旧附件冒充新版本。
