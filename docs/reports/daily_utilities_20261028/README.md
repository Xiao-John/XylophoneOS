# 日常工具组合定向验收证据

本组输入为代码/测试提交 `91f49b0`，系统 build `a89a2a8921e5e2a6`；
配置为 x86-64、QEMU 11.1.2 TCG 单核 512 MiB，GCC 16.2.0、Binutils
2.47.20260726、NASM 3.02。完整源码清单见压缩的系统 manifest；工具源码、
编译器和 ELF 摘要见 tools manifest，SDK/候选 profile 见 lineage。

`du12`、`offline`、`guest_package`、`transactions`、`recovery`、
`package_validation`、`editor`、`xsh_edit` 为各自的真实测试报告；guest 串口
记录按需压缩保留。`xsh_edit_initial_failure` 为修复测试预期之前的失败记录，
对应旧组合镜像，并非最终组合失败。三个 `.log` 为该组合的材料、文档及发行
输入检查，不代表逐成员许可审计或完整发行。各报告的 `not_run` 维持原始范围。

候选 XPK 并非正式发行资产；DU4 ISO 空盘安装和全面逐命令资格尚未完成。
