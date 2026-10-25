# 0045：项目总览、文档清理与 release 准备

2026-10-25。用户要求总览项目、清理不必要文档/遗留，并为下一次 release
做准备；ISO 扩容不在本组负责范围，只登记为阻塞项。

## 清理

- 删除仓库内非 `localpilot/` 的 `.DS_Store` 和 `tests/`、`scripts/`、
  测试 fixture 的 `__pycache__`。
- 新增项目总览 `docs/project_overview.md`，区分当前能力、证据、未完成项。
- 新增 release 准备清单 `docs/releases/next_release.md`。
- 更新文档索引，说明 `work_log/` 是证据而非入口，历史/冻结报告不伪装成
  全绿摘要。
- 不删除 `work_log`、`docs/reports/threading_20261025` 或发行附件；这些是
  证据/发行材料。压缩包归属在总览和 release 清单中说明。
- 删除旧 release 目录下两份**逐字节重复**的顶层源码压缩包
  `xos-0.0.1-1024-gnu-sources.tar.gz` 与
  `xos-0.0.1-1024-gnu-source-supplement-gxx-lrealpath.tar.gz`；canonical
  副本保留在 `build/releases/0.0.1-1024/sources/`，SHA256 分别为
  `e2d91871e39ca50385401776fe2f028965b0f7f8bf129ba2ab70f95325d36911` 和
  `8e8bd6f48ea89845389e803b99249e0275050b1bdc43ff927388ba807e257780`。
  不影响 GitHub 上已有 release assets。

## 发现

- 最近完整 gate 的 build 为 `911184be3f3c99f6`；当前源码重建为
  `f25009cdbb27c857`。A3/A4 install ISO 报告仍绑定
  `26eb667dd8318997`；release 前必须重建 ISO。
- ISO 容量仍受 512 KiB kernel 构建上限、4 MiB 页表和 1 MiB payload 限制；
  不能把 A2–A4 的“从 ISO 文件加载”写成“容量已突破”。
- `scripts/package_release.py` 仍绑定 0.0.1-1024；新 release 需要版本化改造。

## 未运行

没有构建或运行 release；没有删除旧发行附件/源码压缩包；没有修改 ISO
loader/kernel 容量实现。
