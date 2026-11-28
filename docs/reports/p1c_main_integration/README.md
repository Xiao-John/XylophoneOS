# P1-C 主线整合证据

main 3cbb2f35 与冻结 C dea4d6b0 无文本冲突合并。新 native 系统
608aad6ff2fa8b5b 上，两场实际 guest 均通过：初始化 GNU 启动，以及原 PID exec
后产生的 GNU 父／子／孙三代实时撤销。原 C 的 23 场报告保持完整、原字节不变。

| 文件 | 内容 |
|---|---|
| [report.json](report.json) | 父提交、整合范围与结果汇总 |
| [guest.json](guest.json) | 两场实际 guest 的原始成功报告字节 |
| [system_build.json](system_build.json) | 新系统 2,327 项源码、321 项产物及 profile |
| [source_compatibility.json](source_compatibility.json) | 自动合并摘要、各 parent 的保留源、旧 runtime 与新源码差异 |
| [host.json](host.json) | 18 项 authority、46 项 closure、两轮 provisioning、ABI 与登记结果 |
| [authority_host.json](authority_host.json)、[closure_host.json](closure_host.json) | 可移植的完整 host 检查记录 |
| [conversion.json](conversion.json) | 原始报告与日志摘要、转换说明、原证据完整性核对 |

旧 runtime 的原始 manifest 仍为 a7a636…，没有重建或重标。新主线与其原始输入
存在七项内容差异；identity 的三个 ABI 头保持一致。此次资格是冻结 GNU 产物在
新 native 系统上的兼容，不是 K1 新 shared sleep API 或 shared fork 的资格。
没有任意物理掉电声明。

[整合工作记录](../../work_log/6f637e1c_p1c_main_integration.md) 给出完整提交身份、
具体源差异、命令与限制。[manifest.json](manifest.json) 为本 flat 目录唯一
SHA-256 索引，包含本目录的其他全部文件。
