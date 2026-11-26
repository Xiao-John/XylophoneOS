# d1c062ce · 下一阶段组合复验

2026-11-26。以主线 `3b1b4340d2e96b8fb7af9066ccab9fd5ccc35cda` 和树
`1c7016a6d6fd61221801ebc3de10d379b521bd6a` 为空输出重建 BIOS 系统
`8d7525f679d42e69`。复验绑定同一 ISO、同一系统 SDK 和同 SDK 重建的正式 newlib
dash。组合包括当时主线的静态 glibc 基线、QtCore、产品包、Pumpkin 原生服务和
私有区前置代码。后续模块使用各自的源码和客体证据。

| 执行 | 结果 |
| --- | --- |
| `make smoke` 子项，QEMU 11.1.2 | 启动 6、内核 18、任务 12、进程 13、文件 8、持久盘 4、满盘 1、libc 3。libc 客体先通过，随后因宿主串口日志写入空间不足退出，补跑通过。 |
| `e08_storage_smoke.py`、`runtime_smoke.py`、`license_audit.py` | 用相同镜像和实际目标 ELF 在 Linux 复验。QEMU 11.1.3 通过存储 9、运行时 5，许可材料 10、登记 open 0。固定版本内核门禁已由 11.1.2 独立通过。 |
| `pumpkin_daemon_guest.py` | 易失测试配置在 xsh 和同 SDK dash 双入口退出 0，资源恢复为 `129714 / 3 / 1`。 |
| `desktop_product_packages.py` | 同一镜像通过六组检查、五次离线包事务及两应用各自的 xsh 与 dash 客体启动。卸载保留旧文件，图形退出后资源恢复为 `129714 / 3 / 1`。 |

第一轮 Linux 内核门禁因 QEMU 版本不匹配停止。宿主固定版本运行通过内核检查，
但 E08 的宿主导入出现低空间问题。Linux 复验使用独立内存工作盘。首次复验缺少
E08 探针 ELF，补齐了同次构建产物。Pumpkin 测试器要求专有输出在构建目录下，按该
布局执行后导出报告。全程保留原失败记录。

| 工件 | SHA-256 |
| --- | --- |
| BIOS ISO | `0c5393c3224acadeffee5cebe239fcc066fac9bb5863debfeaf6b9d9a4dbae26` |
| 系统构建清单 | `7b368f7eed0c02d412b60241202a4501eb244f8c5262030930eb62c4a3ba48f0` |
| 系统 SDK 清单 | `e5dbd36cc4dc6a4cf689faa540996c22ad6942ba2696ac505b41a976cc11b8cc` |
| Pumpkin 回执 | `a1547708291a008d25467e09a97ed19c6348ed5ec886a40d0993b4502bd86f21` |
| 产品包回执 | `db74665fb7b16ff0342e7d37339817226329bf33f8811e942b0b513dd0a793a6` |

此快照覆盖固定的主线树。QtQml 后续合并、glibc 路径与进程接口、真实持久身份和
WebKit 后续版本进入最终组合门禁时，需在新的主线树重新绑定工件。[阶段计划](../plans/next_stage.md)
