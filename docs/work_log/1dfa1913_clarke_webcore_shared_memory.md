# 1dfa1913 · ClarkE 的本进程软件共享内存

2026-11-27。验收源码 `aa7c18cd` 含当前主线 `643d9de2` 与 #319 的
`6cce7095`。在锁定的 WPE WebKit 2.54.2 上添加 XOS 的原生 `SharedMemory`。
CPU 缓冲由现有 sys88 grant 分配，同一 backing 可有独立只读、可写别名。
句柄与映射持有 backing 引用。最后引用撤销底层 grant。CPU 位图只读映射禁止
写 span 和绘制上下文。没有改动内核权限、syscall 或现有 ABI。
[大小、权限及生命周期边界](../../src/ports/webkit/page/shared_memory_xos.md)

## 真实对象和目标链接

在隔离 Linux arm64、CMake 4.4.5 和 GCC 16.2.0 上重新提取锁定原档，按仓库顺序
零 fuzz 应用 JSC 和四份 WebCore 补丁。使用 #319 的工具链配置启用软件 WebCore。
先生成实际 WebCore、PAL、WTF 及 JSC 头文件。自动构建单个目标对象还会牵引
整套 JSC 依赖，将其暂停后，执行 CMake 生成的同一条 `SharedMemoryXOS.cpp`
目标编译命令。其余 6 个 WebCore 文件、原生 syscall 对象和夹具采用同一目标选项。
使用已绑定的统一 glibc C/C++ SDK、CPU Skia、WTF、bmalloc、字体和编码归档进行
静态链接。生成的 x86-64 ELF `c7e1c0e9…` 没有动态解释器。各输入及工具摘要在
回执中。一般 WebCore 完整目标的编译和链接是另一个验收范围。

在准备相同目标配置时，保留 `CMAKE_EXPORT_COMPILE_COMMANDS=ON`，用
`WebCore_CopyPrivateHeaders`、`PAL_CopyHeaders` 及相关 WTF/JSC 导出目标
生成有效头。使用 `compile_commands.json` 中的目标 WebCore 配置编译
`SharedMemoryXOS.cpp` 和回执列出的文件，再按回执中的归档和位置静态链接。
为客体把输出命名 `shared_memory.elf`，并写入包含 ELF、夹具和补丁摘要的
`target.json`。

## 同一普通镜像的两套客体门

重新构建的普通 XOS 镜像 `8260a61a041b5074` 在 QEMU 11.1.2 TCG 上从 Xsh
运行 WebCore 夹具 3 次，每次覆盖 20 轮分配、RO/RW 别名和对象释放。FAT 读回的
ELF 与链接输入逐字节相同。测试观察实际内核不可提升的只读页、原写者销毁后仍有效
的别名及独立快照。在真实 Skia CPU 存储上绘制并通过 WebCore 位图读取 16×8 的
红、蓝、白三处像素。三次均退出 0，空闲页、任务和完成记录恢复至
`129696 / 3 / 1`。另在同一镜像用既有原生 IP4 夹具等序运行 3 次，实际证明
原生跨进程写入、只读缩权、资源上限及回收。原生门采用分离的旧线程 SDK，其回执
给出实际绑定。公开副本去掉宿主路径命令，保留原件摘要和原始串口。

```sh
python3 -B tests/webkit_shared_memory_guest.py --system "$SYSTEM" \
  --target "$PROBE" --output "$GUEST"
python3 -B tests/ipc_v1_grant_guest.py --system "$SYSTEM" \
  --sdk "$THREADING_SDK" --output "$NATIVE_GUEST" --runs 3
python3 -B tests/abi_doc_consistency.py
```

本轮未验完整 WebCore 绘图上下文、超过 256 KiB 的合并映射或 WebKit2 的跨进程
句柄与回收协议。IP4 原生客体结果只覆盖其现有 ABI。
[目标链接和客体证据](../reports/clarke_webcore_shared_memory_20261127/manifest.json)
