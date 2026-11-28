# P1-C 实际验收证据

本目录记录重新构建后的 P1-C 资格：23/23 次真实 XOS 启动、独立 Linux UID
provider-v2 集成，以及生产 store、authority、closure 和 lease 的 host 检查。

| 证据 | 用途 |
|---|---|
| [guest_report.json](guest_report.json) | 原始成功报告的完整字节；23 次启动与旧/新状态选择 |
| [guest_boots.json](guest_boots.json) | 每次实际 boot 的事务事件、finish code、revision 和原始日志摘要 |
| [system_build.json](system_build.json) | 2,309 项实际源码、320 项产物、显式 300 秒 lease 及 PT_LOAD 相等证明 |
| [guest_conversion.json](guest_conversion.json) | 原始报告摘要、转换说明和运行后完整性复核 |
| [build_bindings.json](build_bindings.json) | 原 GNU runtime、独立 C native SDK 和精确源输入关系 |
| [program_201.json](program_201.json)、[program_202.json](program_202.json) | 两个 generation 的 SDK、源码、ELF 与 manifest 绑定 |
| [provider_report.json](provider_report.json) | 真实 Linux UID 1001/1002/1003 与 SO_PEERCRED；12 项功能检查及 3 项启动计时 |
| [provider_vm_receipt.json](provider_vm_receipt.json) | 实际 VM、QEMU、kernel、initramfs、源码及原日志摘要 |
| [authority_host.json](authority_host.json)、[closure_host.json](closure_host.json) | 18 项 authority 与 46 项 closure 检查；包括普通及 ASan/UBSan |
| [provisioning_host.json](provisioning_host.json)、[launch_lease_host.json](launch_lease_host.json) | store/RPC 权限、持久状态及有限租约检查 |
| [early_diagnostic.json](early_diagnostic.json) | 保留 sys81 枚举误读和 shared fork ENOSYS 的真实失败诊断 |

三代 GNU 进程通过 posix_spawn 创建，父进程先完成同 PID exec。三个实际进程
在撤销前各成功运行叶子，主管随后提交真实撤销，三代均拒绝后续启动。另一组
在 daemon 停止后拒绝启动。shared GNU fork 仍为 ENOSYS，归独立 P1-K2，
这里没有声称通过。两个 generation 使用同一探针代码和不同的根/路径，
证明的是 catalog 选择与完整闭包启动。

XOS 故障矩阵使用 production Files/daemon/loader 与 developer authority，
在 CAS/ACK 边界注入拒绝、已提交但结果未知及未提交且结果未知。独立 Linux
provider 使用真实 UID，单独验证权限、CAS 和进程重启。两种资格分别记录；
没有以 sync/reboot、停止 QEMU 或 host kill 声称任意物理掉电通过。

原程序构建清单仍为 built_not_run，runtime 为 public_runtime_built_not_run；
匹配字节的实际运行证据在 guest 报告中。原 GNU runtime 绑定其 F GNU SDK，C native SDK 仅用于
应用 bootstrap，没有更改或重标原始 manifest。完整复跑方法与故障解释见
[工作记录](../../work_log/d7afe98c_p1c_catalog_authority.md)。

[manifest.json](manifest.json) 是本 flat 目录所有其他文件的唯一 SHA-256 索引。
