# COW0 源码审计与 eager 基线

审计基线 `9c51eb46e321e0f2aee7837b00e90d5733ad9cfb`；本次仅冻结
[COW0 契约](../../contracts/cow0.md)，未实现或启用 COW。可复核清单为
[source_audit.json](source_audit.json)：46 个 `copy_to_user` 调用点、6 个物理
直映候选点、13 个源码文件的 SHA-256。逐点分类见契约；扫描无法证明没有别名、
汇编或未来新增的间接写，必须结合人工审计。

复核命令：

```sh
python3 scripts/cow0_source_audit.py --check
python3 tests/cow0_source_audit_test.py
python3 tests/docs_consistency.py
python3 tests/abi_doc_consistency.py
python3 tests/ipc_v1_reference_model.py
```

上述检查均通过。`--write` 仅接受与脚本中声明基线逐文件一致的源码，防止将变化
后的源码误标为旧基线；后续刷新需先审阅变更并选择新基线。单元测试覆盖发现新写点、
变更检测及拒绝误标基线，不是 COW 客体验收。

[validation.json](validation.json) 记录本次实际运行、镜像/ELF/回执摘要、QEMU
命令模板、检查项和资源基线；四份 `.serial.log.gz` 是对应客体的原始串口字节，
压缩包和解压后摘要均记录在回执。`*.manifest.json.gz` 为去除主机路径后的构建
清单子集（保留源码和产物摘要）；回执另外记录原始本地清单 SHA-256，不将子集
冒充原始清单。命令中的 `${WORKSPACE}`、`${TEMP}` 是路径模板，不是实际执行命令。

在 GCC 16.2.0、Binutils 2.47、NASM 3.02、QEMU 11.1.2 下，以现有 eager 代码
构建正式镜像 `154e39fe4d1fa205` 和探针镜像 `6301094dad0e3b47`。实际客体通过：

- 正式镜像 VM1 私有探针关闭检查；
- VM2 续体、pin、取消及资源回收 10 组；
- VM3 eager fork、exec、两轮分配失败回滚及取消 3 组；
- xsh/dash libc 映射及真实故障 6 项。

镜像清单生成后，仅 COW0 审计脚本和其单元测试有变更；两份清单中全部 `src/`
摘要仍与当前工作树一致。dash ELF 来自此前 SDK 构建，不能当作当前 SDK 的重新
资格认证。IP2 已实现但其独立真实客体资格未由本次建立。上述测试不能证明 COW
行为；COW1–COW3 的失败矩阵、全部 V1–V7 正式资格及性能对照仍须在对应阶段完成。
