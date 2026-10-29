# PX4-A 独立设计认领与源码审计

2026-10-29。基线 fetched upstream `aaec2e9d8ffe61ce1d523cd56852d36cde3edd07`（PR #17已合入）。
**设计已交付；公共匿名VM实现/客体验收 BLOCKED 于维护者审查合入登记。**
没有实施67、修改内核/libc/SDK或运行新镜像；不复用旧报告为本分支资格。

[契约提案](../../contracts/anonymous_vm.md)定义sys_vm67的64字节只读请求、
6项操作、数值错误域、匿名地址图、片段/提交配额、W^X/NX/guard、等待pin、
失败原子性和V1–V7真实验收。它是本分支的claimed提案，不是全项目已分配ABI。
PR #18 的设备112属于独立网络负责人，未挪用。网络未完成不妨碍匿名VM设计。

## 固定来源与实际发现

[机器审计回执](source_audit.json)逐文件记录字节SHA256、真实symbol行号与源URL；
原始V8缓存位于另一个只读phase1工作区，未修改其字节。已对原phase1 lock中的
3份V8输入逐文件复核；额外3份固定同V8 SHA的文件重新获取，source audit保留结果。
额外 `src/heap/heap.cc` 下载发生SSL EOF，未使用该缺失文件作结论。官方Issue8三个
VM函数页面本轮web读取403；保留失败，标准条款核对未宣称通过。

| 实际来源/调用点 | 查实的前置和设计响应 |
|---|---|
| kernel core/memory.cpp allocate_page121、release_page147 | 512MiB管理上限、分配清零、释放不清零；所有重新commit仍须分配清零，暂存/页表也计实际物理消耗 |
| paging.cpp map_page_in52、unmap_page_in119 | ensure_table逐级分配，后续失败可留下中间表；当前unmap只在旧1GiB窗口回收空PT；新事务必须记录新表并回滚/回收所有层级 |
| paging.cpp copy_user_pages_in190、create250、destroy288 | 用户窗口仅PDPT[1]；仅复制present页；NONE持页/高arena需显式所有权遍历，不能把旧destroy套到新高映射 |
| tasks.cpp user_range_ok268、heap_break1018 | 用户指针检查硬限1GiB；brk只有固定256MiB堆，不能靠包装获得稀疏保留或保护 |
| tasks.cpp pinned_range1098、wait_word1376 | pin不止word，还含process_wait和join输出；protect降低写权限亦须busy，不能只拦unmap |
| tasks.cpp prepare_fork1429、exec1559/1588、destroy746 | 线程SDK继续拒绝fork/exec；旧单线程eager-copy与exec事务须扩展VMA归属、失败回滚和新空间退出 |
| loader/load.cpp process_create196、process_map235/255/263、abort288 | 真实ELF读取和策略在用户态；不把ELF/JIT业务搬到内核 |
| loader/elf.cpp LOAD分支61、权限84 | 当前静态ELF低窗口且拒绝W+X；匿名arena独立，不静默重定位旧ELF |
| libc newlib_syscalls.cpp1548/1549 | mmap/munmap真实ENOSYS包装；不存在已验匿名映射 |
| V8 platform-posix.cc459/500/534/637 | 对齐分配会释放首尾；SetPermissions真实mprotect；Decommit用MAP_FIXED匿名重映射；XOS首版不开放任意覆盖，需要显式平台适配 |
| V8 include/v8-platform.h568/576/589/599 | protect、recommit、advisory discard和保证重提零页的decommit语义不同；不能统统空成功 |
| V8 sandbox/sandbox.h51、113 | 1TiB区及前后32GiB guard、低4GiB不可访问目标；当前ELF落在低4GiB是另一安全阻塞，不能仅有mmap就称V8可用 |
| V8 page-allocator.cc45/145/161 | 实际PageAllocator进入OS Allocate/SetPermissions/Decommit；首期不要重写整个引擎 |

V8固定SHA `bb294624702efbb17691b642333f06bf5108e600`，由Chromium
`4b8153ab58d3c3f4c9f7e4baad9616ecf80db5fa` 的既有来源矩阵约束。
本轮只核其内存调用点；没有完整V8编译、JIT、WASM、Chromium、DOM或Code运行证据。

## 复现与结果

```sh
python3 scripts/px4a_source_audit.py \
  --v8 ../XylophoneOS-modern-app-phase1/build/modern_apps/sources/v8 \
  --extra build/modern2_px4a/sources \
  --source-lock ../XylophoneOS-modern-app-phase1/docs/reports/modern_apps_20261029/source_lock.json \
  --output build/modern2_px4a/NEW-source-audit.json
python3 tests/docs_consistency.py
python3 tests/abi_doc_consistency.py
git diff --check
```

额外源可从source_audit中每个固定SHA URL加 `?format=TEXT`获取并base64解码；
核验sha256后置入 `--extra` 对应路径，fetch.json保留所有原始失败；工具不执行第三方源。
命令实际结果见[validation.json](validation.json)。这只是文档/源码审计检查，
`guest_status=NOT_RUN`。没有系统镜像、ELF、QEMU命令、资源样本或截图可冒充本轮客体验收。
下一实施PR须从新来源重建并逐项生成这些回执；旧Qt/线程/ELF资格仅作回归测试设计来源。

## 接续与审查关注点

维护者需裁定67认领、6操作/错误域、16–32TiB arena和工程限额，以及EBUSY偏差。
新内核续体与调度安全点、完整pin覆盖、NONE持页所有权、高页表fork/exec/销毁和W^X
同时是实施前置；不能将这些拆掉只做mmap的成功返回。登记合入后独立实施，V1–V7未通过
前不置SDK支持位；不自行批准/合并。完整共享内存和动态链接器仍另设阶段。
