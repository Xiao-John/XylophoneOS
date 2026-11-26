# d1cc3ab7 · Pumpkin snapshot publication

2026-11-26 · 从 `b93da33c` 继续。实现私有 `snapshot_publication`，把受信槽 I/O
和受保护发布记录组合成 P0 现有 `store_api`。先校验当前记录和选中槽，再写入、
同步并核验非活动槽，最后对完整前一记录执行比较发布。选中槽不一致时拒绝加载和
写入。配对端点与工作盘路径审查、files 方案和独占设备方案见
[私有对象与快照发布](../contracts/pumpkin_snapshot_publication.md)。

## 验证

宿主使用 Python 3.12.15、Apple Clang 21.0.0，目标对象使用 x86_64-elf GCC 16.2.0。

```sh
python3 tests/pumpkin_host.py --target-cxx x86_64-elf-g++ --output build/pumpkin_publication/host
python3 tests/pumpkin_host.py --sanitize --output build/pumpkin_publication/sanitized
python3 tests/abi_doc_consistency.py
```

宿主正常和 ASan/UBSan 各通过十二组，其中四组新增发布检查：

1. 验证写入顺序和旧版本比较，使用两个真实临时文件作为数据槽。
2. 模拟同步失败、写后读回错误、确认未提交及新旧两种不确定提交结果，按发布记录恢复。
3. 模拟更换数据字节而保留独立发布记录，拒绝陈旧版本及同版本同长度但摘要不同的快照。
4. 重建发布器和身份核心，从临时文件恢复同一账户身份，验证吊销仍有效。

文件槽经宿主 `fflush` 和 `fsync` 写入，发布记录由 fixture 单独在内存中持有。
重新构造消费端不会清空 fixture。未执行真实发布记录断电、跨宿主重启或介质原子性验收。
新模块通过 x86-64 freestanding 对象编译。现有 ABI 一致性通过。
上轮的普通 files 会话、FAT 存留和 QEMU 证据仍以
[a5bdbae1](a5bdbae1_pumpkin_storage_feasibility.md) 为准，本阶段未重跑这些试验。

| 工件 | SHA-256 |
| --- | --- |
| `build/pumpkin_publication/host/pumpkin_publication_host` | `fef807b1a632d801e01a751e15f72c8f74b355a69514e37f6e09fd9c3e6d8a65` |
| `build/pumpkin_publication/host/snapshot_publication.o` | `5b3f6f3b62c8bd4e220e151be2bb2a8690c41e30a3ea6f84ffce44206e0b8484` |
| `build/pumpkin_publication/sanitized/pumpkin_publication_host` | `035cd8d3e4c9f3e97b1c3e2828a426e94de727addfb48e5db0542cb96e7ab8dc` |

## 交接

先审 files 私有对象的授予入口和路径兼容，再冻结 IPC 编码。并行确认能够提供持久
原子比较替换的独立代际来源。客体后端接到发布器前需要分别证明对象复用、独占租约、
FAT 别名与离线路径兼容，以及在实际同步和提交故障点恢复正确代际。本阶段不改变
共享 ABI、files 默认路径和 P1 守护进程调用方式。
