# FB1/FB2 双 Shell 定向验收

2026-10-29，基于包含 VirtIO-GPU PR #16 的主线 `39083f9`，系统构建
`f87bebabb97dc166`。系统源码与产物哈希见 `system_manifest.json.gz`；dash 源码、SDK
和产物哈希见 `dash_manifest.json`。报告、串口日志及实际导出包保存在本目录。

`xsh_report.json` 记录 xsh 原有14项 FB1/FB2 检查；`dash_report.json` 记录 dash
正常退出、缺失命令、page fault报告及同一独立程序的xsh调用。dash故障报告四文件
已验证格式和实际目标ELF的摘要。宿主符号解析不依赖客体Shell。测试在专用FAT工作盘
和QEMU执行，不代表真实硬件或所有故障模式。

两份 `attempt_*.serial.log.gz` 保留修正前失败：普通dash外部命令无启动授权；
子shell使用exec时，旧freestanding CRT缺少exec ABI标记。最终独立程序改用支持
exec的libc CRT，并通过子shell继承已有权限；不按程序名称授予新权限。
