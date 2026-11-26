# 955ab8a3 · Pumpkin 独立代际 files 存储适配器

2026-11-26 · 从 PR #199 合入后的 `a4dd121b` 开始。用现有 files 槽框架和 `snapshot_publication` 组合独立代际源与真实账户核心，定义 [files 快照与独立代际接合](../contracts/pumpkin_anchored_files_store.md)。本轮保持原可重启测试走本机双槽，接口只在 Pumpkin 内部。检查 sys81、sys84–86、sys82 及 sys112 后，明确真正客体到宿主的受保护、独立字节通道仍需接入。普通终端无法充当该信任边界。

```sh
python3 -B tests/pumpkin_anchored_files_host.py --target-cxx x86_64-elf-g++
python3 -B tests/pumpkin_disk_test_store_host.py
python3 -B tests/pumpkin_disk_test_store_host.py --sanitize
python3 -B tests/pumpkin_generation_authority_host.py
python3 -B tests/abi_doc_consistency.py
```

在真实 APFS 临时目录，用 Python 3.12.15、Apple Clang 21.0.0 编译 C++ 核心与适配器，通过真实 Python 独立代际实现和另一个文件内的两个槽运行。每次操作启动新进程，槽写入调用实际 `fsync` 及原始字节读回。通过 6 组。首次配置、合成登记、重启进程后认证均成功。非活动槽读回失败保留原认证。实际吊销提交后丢失回复，核心停止，重启进程拒绝凭据。恢复旧槽镜像或放入相同修订不同摘要的有效 P0，均拒绝认证前的启动。缺少活动槽、无权威记录及非活动槽损坏也按各自边界处理。所有账户和凭据均为测试输入。

GCC 16.2.0 freestanding 编译适配器、既有 native files 客户端与原测试存储通过。原槽选择器普通及 ASan/UBSan 各 2 组、独立代际组件 8 组、ABI 一致性检查通过。首次 ABI 检查缺少稀疏检出的 `e04_loader_sdk.md`，加入该输入后通过。

| 宿主组合证据输入 | SHA-256 |
| --- | --- |
| `anchored_files_store.cpp` | `f5f8f00f888dd74646156e4f05bcb3103c89a77e599f3c854685434987e29584` |
| `anchored_files_store.hpp` | `4de513e089ef73513f9144dc424be22cf79015f8b5988c2b99bc44e2ebabfdc9` |
| `disk_slot_frame.hpp` | `7bccf5f75832341563fccec3b9195900884cf6ce48fcdf9b0d1750fcd87e24f7` |
| `anchored_files_store_host.cpp` | `309a222f5f338b7e958a753f2b600b610d6cdf174156f594630b8b9f1106a406` |
| `pumpkin_anchored_files_host.py` | `8f726db5d4b07e336ba8c4315e9d2aad95a113b3d1d825edf9b32e2ea031972c` |

宿主槽回调模拟授权完成后的读写语义。实际客体 files 租约和宿主代际服务的共同运行、只恢复旧工作盘的客体重启、物理断电和生产部署资格均未运行。
