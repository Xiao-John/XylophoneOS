# ea2d71c6：下一阶段组合客体复验

2026-11-26。从候选提交 `d155a61f35c5cdfb15e8f9163c4b4ae19eee13e9` 的
干净源码重新构建。Git 树为 `70dd861489a523dbf2c084f0ea9511230b6240b4`。
该树组合了当时的文件路径变更、glibc 管道与 dash 两种启动入口、Pumpkin 客体候选、
ClarkE LLInt、Mobius glibc 会话与软件包，以及基础工具的前台迁移候选。
测试记录对应此提交。后续的 `/dev` 保护、here-document 重定向预检和
Pumpkin 快照阻塞控制各有独立复验，最终主线仍需按实际提交重新绑定。

macOS QEMU 11.1.2 的系统构建为 `7ff8eba2295e9bf9`。`make smoke`
通过 79 项常规检查，另通过 10 项许可材料检查。Linux 从同一源码重新构建，
与 macOS 构建的普通 ISO 按字节一致。Linux 使用 QEMU 11.1.3 和重新生成的
静态 glibc C SDK，验证路径变更 2 次、管道 2 次、进程启动及回收 6 次、
两种 dash 入口共 40 次。FD 与真实文件服务/FatFs 的 15 组宿主集成测试、
SDK profile 的 44 项宿主检查和 ABI 检查通过。

| 产物 | SHA-256 |
| --- | --- |
| macOS 系统清单 | `459dad654f3d44b26b51d56f67e1683fc249921bd3563508b9381e61868debee` |
| Linux 系统清单 | `cfcd3434adc58b244e25106b688d75857fa68f5367a170444babcf20531724bb` |
| 普通 ISO | `fcdb84345d8af6a2d71f940ec04c25a25968caac998e4f7ad719a40855af6752` |
| 静态 glibc C SDK 清单 | `4b6df9f51b5c72fd0091cd97bacbc753590ef09a18f40387947c8176c8627b37` |
| 显式 glibc profile | `e5abaf7805e5e4d4247cc346f8fe9e81153a8a8643bfc60cfd8f2c1a33334e0b` |
| 常规检查日志 | `30c6ffa153d0ce685444f56e2c7ec4701249a65b436e38ce887c6b71e27066f3` |
| 路径变更报告 | `83deb1ff9b3fd176c49e3c29724337961cc3f96243756af14149882f1a043b6c` |
| 管道报告 | `43370c422f05979a1edca05a37e1d71979d0afa1b6f45f59105a9d8ebb7a83bb` |
| 进程启动、等待及回收报告 | `a145d5bb6cce8475c9d7a43dba2214f8d863b4d09ffb582efb4bc3290c1c99c9` |
| dash 双入口报告 | `45c7830a6ad5fe738bbab891b9284cd028b6a659cee5acde47364b8d0b5508b6` |
| 真文件服务集成日志 | `f3eace02d29627d18b682e69235fa48bb9b10755fa57b22281adab172a20b96c` |
| SDK profile 测试日志 | `0332cf5a4b2095e0157297fd35a7c528d73ccae9c28d7739ac3f0f8b527dc3f6` |
| ABI 检查日志 | `e2e4c52a0306922418b0917ef27cc47d9eba2bec406bbb9f4f1387b8c86eb301` |

原始日志与运行入口位于该 worktree 的 `build/combination-d155a61f35c5/`。
显式 profile 只声明 `directories`。`spawn_delegate` 的探测触发其缺失能力检查，
动态链接、POSIX 进程组、默认 SDK 切换、Pumpkin 生产认证和 ClarkE 完整引擎仍需各自验收。
