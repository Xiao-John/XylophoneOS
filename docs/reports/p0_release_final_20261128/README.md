# P0-R1 最终 glibc 静态发行组合

本目录记录 2026-11-28 的新一轮真实验收。技术资格已通过；这里保留的是上传前
冻结结果，公开 Release 的下载地址和远端资产摘要由最终交付记录登记。
[qualification.json](qualification.json) 是结论入口，
[delivery.json](delivery.json) 记录精确交付集合和外层归档身份，
[90c2ce10 工作记录](../../work_log/90c2ce10_p0_r1_final_distribution.md)
说明构建步骤、失败尝试、修复与边界。

## 资格与绑定

| 对象 | 实际结果 | 回执 |
| --- | --- | --- |
| 候选系统 `7c8c59058be0b5f1` | 普通 smoke 79 项、登记许可材料 10 份、安装器及 stock guest 通过 | [candidate.json](candidate.json)、[installer_guest.json](installer_guest.json)、[stock_guest.json](stock_guest.json) |
| 最终 C/C++ application kit | glibc 2.44、GCC 16.2.0 C++ 静态运行库构建和上游输入验证通过 | [sdk_builds.json](sdk_builds.json)、[glibc_authentication.json](glibc_authentication.json)、[gcc_authentication.json](gcc_authentication.json) |
| 实际发行盘 | 包安装、普通冷启、Python/压缩/IDNA、原生卸载及用户数据保持通过 | [package_guest.json](package_guest.json) |
| 原生 GNU 工具 | 20 个场景通过，包含预期未定义符号链接拒绝；其余 19 项退出 0 | [native_gnu_guest.json](native_gnu_guest.json) |
| 对应源码及接收材料 | 140 个组件源记录、五组接收者、17 个静态程序原版及单成员 libc 替换通过 | [component_sources.json](component_sources.json)、[receivers.json](receivers.json)、五份 `*_relink_guest.json` |
| 升级恢复 | 同步检查点 123 中断、恢复原数据库/索引/用户数据、重试及冷启后 58 文件通过 | [upgrade_guest.json](upgrade_guest.json)、[fault_build_comparison.json](fault_build_comparison.json) |
| 独立冻结 newlib 往返 | 四次冷启、六次程序执行、15 个 SDK/profile 保护检查通过 | [frozen_roundtrip.json](frozen_roundtrip.json) |
| 最终冻结 | 20 文件，原 15 项资产字节不变；重开归档及错误输入拒绝通过 | [pipeline_receipt.json](pipeline_receipt.json)、[preflight.json](preflight.json)、[delivery.json](delivery.json) |

此 R1 application profile 为 `xos-x86_64-glibc-p0-20261128`。制作该发行盘的 XPK
须显式使用归档中的 `application-sdk/xos-app`。新宿主 SDK 的 Actions 构建拥有
独立的 manifest、tree 和 profile；两个默认包 profile 不可互换。新 GCC 16.2.0
源归档、签名及钥匙环随新宿主 SDK 的源码材料交付，R1 的历史 GNU Seed 源归档
不代替这些新 C++ SDK 来源。

系统清单的 2,211 项源码与公开提交 `819ea63ae84b1e89862648af002c2a09d1936c02`
逐项相同，同一系统的 native/IPC/deadline/stdio/ABI 门见
[最终集成证据](../p0_integration_final_20261128/README.md)。这项对应只覆盖登记的
构建输入；原生产者提交 `3964200d524fd39f3a95c166800832623c5f3591` 保持原记录。

## 公开导出与核验

报告是有明确来源摘要的派生副本。宿主位置及客体命令路径使用 `XOS_*` 变量
表示；原始日志本地保留，其摘要仍在回执中。本目录不附带串口或 receiver 日志，
也未复用历史未获准公开的附录。[export_provenance.json](export_provenance.json)
保存原始与导出字节映射；原始回执中的产物摘要始终指原产物，不能当成派生副本
的校验值。本目录文件的完整性统一由平铺的 [manifest.json](manifest.json) 覆盖。

发行归档中的三份 smoke 另有自己的公开副本与组合绑定，见
[smoke_publication_binding.json](smoke_publication_binding.json)。它们与本目录
导出采用各自记录的摘要。源/重链接归档及原 GNU 供体保持验收字节，其中固定
工具链前缀与历史构建路径不被改写；不能把结构化报告的路径检查结果推广为所有
不可变源归档和二进制都已清除路径。

从仓库根目录核验本目录：

```sh
python3 scripts/verify_evidence_index.py docs/reports/p0_release_final_20261128/manifest.json
python3 tests/report_manifest_check.py
python3 tests/check_public_evidence_paths.py --index --base origin/main
```

许可范围为 `registered_materials_and_sdk_copies`，台账为 0 active open、
1 deferred、7 not-applicable；这不表示所有许可问题已经解决。物理掉电、扇区
撕裂、该宿主网络命名空间隔离、任意动态加载、全量 POSIX、未随包 CPython
扩展及 GUI 资产未在本静态发行资格中声明通过。动态资格由对应 R2/R3 报告承担。
