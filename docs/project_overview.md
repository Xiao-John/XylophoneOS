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
- xsh 原生入口；dash 0.5.13.5 的 B0/B1/B2 受限功能，C 阶段未完成。
- file-backed El Torito ISO：`KERNEL.BIN` 从 ISO 读入，dash 作为 payload
  自动安装；0047解除旧容量限制，kernel文件8 MiB/内存16 MiB、payload32 MiB。
- CPython 3.14.9 PY0/PY1 与 T3-PY 真实 pthread/GIL gate。
- xypm P0/P1：宿主候选盘 install/upgrade/remove、客体只读 `list/info`；
  P2-1维护准入/文件写租约与失败关闭已验。
- Open Adventure 在 XOS 内构建的受限验证；完整游戏/文本门未收口。

## 当前证据

- 最近一次完整 gate 的系统 build：`911184be3f3c99f6`；基础镜像
  `d9b81936924e729d2cf059d936b2406828a6785c151246603ed77ec9b2c5121d`。
  当前源码（含 T3-PY gate 文本、xypm 脚本等）重建为 `f25009cdbb27c857`，
  需要重跑全量 gate 后才能作为 release 回执。
- dash B2：6/6；B0/B1 回归 7/7；见 `work_log/0042_dash_b2.md`。
- CPython T3-PY：5/5，资源 `[129833,2,0]`；见 `work_log/0043_cpython_t3_py.md`。
- xypm：P0 宿主 16/16、P1 宿主 12/12、双 Shell/重启客体 10/10；见
  `work_log/0044_xypm_p1.md`。
- 0047 ISO：大容量10/10、正常兼容4/4。5.6 MiB真实kernel和2.1 MiB载荷
  完整验证；正常共同build4c79f3a789dcff61位于build/iso_capacity/normal。
- 0048 P2-1：在共同build上8/8，资源[130345,2,0]；该build全部src/摘要匹配。
  旧综合/应用回执没有因此重新取得当前build资格，release仍需统一冻结/验收。

## 明确未完成

- CPython T3-QT、SMP、完整 POSIX/pipes、信号/终端语义。
- xypm P2原生包验证/持久日志/客体写命令（已有P2-1门控）、P3签名仓库；dash C阶段。
- Qt 实现、UEFI、完整 release 打包/签名。
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
