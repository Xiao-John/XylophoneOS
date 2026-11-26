# 518373ea · Pumpkin 独立代际客体验证

2026-11-26 · 从 `f3c5150b` 继续，使用 `aac17b8e` 本地提交构建 [专用无界面开发配置](../contracts/pumpkin_anchored_guest.md)。可信监督器、内置代理与真实守护进程使用现有 COM1、IRQ4、sys81、sys84 和 files 独占租约。宿主独立记录保存在工作盘之外。首次开发启动发现 `image_info.name` 只有 16 字节，长模块名无法精确查找。改为 `p2_anchor_proxy` 后运行通过，并从已提交源重新构建复验。

```sh
python3 -B scripts/build.py --pumpkin-anchored-probe --output-dir build/anchor-final-system
python3 -B tests/pumpkin_anchored_guest.py --system build/anchor-final-system --output build/anchor-final-guest
python3 -B tests/pumpkin_anchored_files_host.py --target-cxx x86_64-elf-g++
python3 -B tests/pumpkin_disk_test_store_host.py --sanitize
python3 -B tests/pumpkin_host.py --sanitize
python3 -B tests/pumpkin_generation_authority_host.py
python3 -B tests/abi_doc_consistency.py
```

QEMU 11.1.2、x86-64 BIOS、无网络。三个阶段均发出经过受信启动授予的独立代际消息。首次启动使用真实 sys63 生成凭据，检查错误及正确认证、活动会话、吊销后会话与旧密钥均被拒绝。宿主在修订 2 盘同步和读回完成后、向客体确认前，保存并逐字节核对完整旧盘。随后成功提交修订 3。记录在每次 QMP 退出后保持修订 3。

第二次启动使用当前工作盘，独立源只收到一次修订 3 读取。客体实际启动守护进程，登记查询确认吊销仍在。第三次启动使用完整旧盘，同样只读一次修订 3，内核认证的启动控制握手成功，随后实际守护进程退出 11，未进入认证。两次恢复都核对了整个输入和输出盘的 SHA-256 相同。

宿主独立代际测试 8 组、适配器组合测试 6 组、原槽选择器 ASan/UBSan 2 组、核心含发布器 ASan/UBSan 13 组、目标对象编译和 ABI 检查均通过。未在该配置运行 dash。完整重启不携带首次测试密钥。真实线路中断和掉电、宿主目录同时回滚与生产硬件资格不在此客体验证范围内。

| 工件 | SHA-256 |
| --- | --- |
| 系统 `db9e481e59d4126f` manifest | `47424231f923f4ab3c0d6f4ff8642d8f3c09f819d6951d6d011def6d69709b86` |
| 系统 ISO | `2c61e93cb2ac41774ed52b086f14a2fc9863e37c8b3bcc9e6375a45b007004db` |
| SDK 树 | `11c2f3201135c5b4108572159f6bdee5e8646ec6f3eee1bba438d55d86925f3f` |
| 守护进程 ELF | `44a2e47e6dc5738bf133453a8bf8b9e087403d6c2ebb0051b97e18e2084c30e7` |
| 串口代理 ELF | `afd204abf1b4358bcba2b85a3613563ffaee9f6ee5632b51afdae81135d8d43c` |
| 健康盘 | `a496b5a7182b5cafc7c6a5112821db013d3ddd2f195030813906af30536c7635` |
| 复原旧盘 | `834f1dfa35c3af7e849a85a882803add98727c3a90f19a6b213ced780bcc6ca1` |
| `build/anchor-final-guest/report.json` | `b672697f364bc77787a90787effdb141edd0f412c3fe50371877bd7a74a59499` |
| `build/anchor-final-guest/cycle_serial.log` | `cca6d9a1052ca2bf290db53eec2e5150d7e9e5a5b4580054ecd21a91c57eec91` |
| `build/anchor-final-guest/healthy_serial.log` | `7f3697a824a2fbb9b49f505b31b0ec7cd4317719cfc97a2b686bfe364ead9819` |
| `build/anchor-final-guest/stale_serial.log` | `e90e706bf4d663e41d736871a4979a634b684036a000e5cba0f17035e1e6947d` |
