# cd9e44fb · Pumpkin independent host generation authority

2026-11-26 · 基于 `42552a7b`，实现 [开发配置宿主代际组件](../contracts/pumpkin_host_generation_authority.md)。组件在一次性客体盘之外的私有目录保存完整代际记录。显式创建空记录、比较后逐代推进、串行写入、文件与目录同步和回读均走实际文件系统。测试数据为固定虚拟安装域、生成摘要及空 P0 快照，未使用用户凭据。

```sh
python3 -B tests/pumpkin_generation_authority_host.py
python3 -B tests/pumpkin_host.py --target-cxx x86_64-elf-g++
python3 -B tests/abi_doc_consistency.py
```

macOS 27.2.1（26B131）、Python 3.12.15，在内部 APFS 的一次性目录执行宿主代际组件测试。8 组重复通过。两个真实进程以同一旧记录竞争，等待中的写者在第一个提交后得到冲突。分别在替换前、替换后目录同步前、目录同步后回读前执行 SIGKILL，新进程恢复精确修订。还覆盖暂存及目录同步错误、错误或缺失记录、版本上限、完整比较以及仅替换盘侧快照字节后的独立代际保留。现有核心 13 组和 GCC 16.2.0 目标对象编译通过，临时编译文件使用 16 MiB 内存盘。ABI 一致性通过。

| 输入 | SHA-256 |
| --- | --- |
| `scripts/pumpkin_generation_authority.py` | `8a9521df7c5aa5c38396183f0fcb16a98fa2dae1746b73d82037b408b1e2d706` |
| `tests/pumpkin_generation_authority_host.py` | `14df76b73522d595da02092527c97a2b78775145b1eb68ecc19d09a175ab29b7` |

下一步按契约接入显式客体 profile 的受保护通道，固定真守护进程、files 租约和宿主安装域，在只恢复旧客体盘时验证启动和认证拒绝。物理断电、整机重启、其他宿主文件系统和客体接入未运行。
