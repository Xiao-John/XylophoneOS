# E08-0 审计：先量清楚，不先写编译器

状态：**审计完成；E08 未完成，E08-1 未开始**。本阶段没有改内核、文件服务、
libc 或工具链，只测量和定停点。证据：`build/e08_stage0_audit.json`，
生成脚本 `scripts/e08_stage0_audit.py`。

## 固定版本

| 项目 | 值 |
|---|---|
| GCC/G++ | 16.2.0，target `x86_64-elf`，`--disable-nls --without-isl --without-headers` |
| Binutils | 2.47.20260726（安装树 2.47） |
| newlib | 4.6.0.20260123 |
| QEMU | 11.1.2，qemu64 / 64 MiB / 单核 |
| GCC 源码包 | `gcc-16.2.0.tar.xz` 107,200,820 字节 |
| Binutils 源码包 | `binutils-2.47.tar.xz` 29,034,716 字节 |

版本先冻结；如后续改版本，重新做本审计，不拿版本字符串相同当二进制相同。

## 实际测量

| 对象 | 实际值 | 说明 |
|---|---|---|
| `cc1` | 40,163,440 字节（约 38 MiB） | Mach-O arm64 宿主程序 |
| `cc1plus` | 42,714,480 字节（约 41 MiB） | Mach-O arm64 宿主程序 |
| x86_64-elf GCC 安装树 | 201,359,486 字节（约 192 MiB） | `du` 约 189 MiB |
| Binutils 单工具 | `as` 1.76 MiB、`ld` 2.58 MiB、`ar` 1.04 MiB 等 | 全是 Mach-O arm64 |
| Binutils 安装树 | 23 MiB | 本审计只求和主要可执行文件 9.7 MiB |
| newlib 预构建包 | 10 MiB（libc.a 6.4 MiB、libm.a 2.6 MiB） | target x86_64-elf |
| 当前工作盘 | 16,777,216 字节（16 MiB） | FAT16，独立于 build/ |
| 当前文件上限 | 4 文件 × 24,576 字节、8 打开 | RAM staging |
| 当前进程上限 | 64 用户页 = 256 KiB、8 任务 | QEMU 64 MiB |
| 当前启动镜像上限 | 512 KiB | 内核文件约 256 KiB |

## 关键发现

1. **宿主工具不是 Seed。** `cc1`/`cc1plus` 是 Mach-O arm64，目标是
   x86_64-elf；即使它能生成正确 ELF，也不能在 x86_64 XOS 里执行。需要
   Canadian cross（build/host/target）或等价的原生 Seed 构建路径。
2. **体积超过当前盘/进程上限一个数量级。** 仅 `cc1` 约 40 MiB，当前工作盘
   16 MiB、进程 256 KiB；把二进制塞进 512 KiB 启动镜像更不可能。必须先决定
   更大工作盘和更大的用户地址空间/装载策略。
3. **C++ 运行库缺失。** `libstdc++.a`、`libgcc_eh.a` 不存在；当前 G++ 只能
   生成目标代码，不能链接一个真实的 C++ 程序。异常/RTTI/TLS 是单独决策。
4. **编译器需要的文件语义没有。** 子程序只有 0/1/2 控制台句柄；libc 的
   `open/stat/unlink` 返回 ENOSYS；没有 per-process 文件会话、路径、临时文件。
   编译器无法读源码、写对象或使用临时文件。
5. **编译器需要的进程语义没有。** 没有 fork/exec/waitpid/pipe/环境变量；
   GCC driver 启动 `cc1`/`as`/`ld` 的路径无法照搬。
6. **宿主依赖不能直接搬。** `cc1` 动态依赖 libiconv、MPC、MPFR、GMP、zlib、
   zstd、libc++；XOS 没有这些宿主库，也不能把宿主库混进 sysroot。
7. **64 MiB/8 任务不是按 GCC 定的。** 即使磁盘解决，cc1 的地址空间/峰值
   内存、子进程和临时文件仍需要单独的容量决定；不能静默把 QEMU 调到“够大”
   就宣称可运行。

## 审计结论

E08-0 的结论不是“现在可以搬 GCC”，而是：

> 当前配置离原生 GCC/G++ 还差存储、文件会话、进程/IO 语义、C++ 运行库和
> Seed 构建路径；直接下载 GCC 源码开始 configure 只会得到不可运行的宿主工具。

因此 **E08-1 暂不开始**。以下决策必须先做，且应作为下一轮的显式范围：

- 工作盘候选：至少 512 MiB、FAT32，专门盘，不当 `build/` 或日常耗材；
  最终值由 Seed/源码/构建产物的实测峰值决定。
- 用户进程/内存：是否提高 QEMU RAM、进程页上限，或采用按需装载/分段加载；
  不能继续假定 64 页能容纳编译器。
- 文件：流式替换取代 24 KiB RAM staging；per-process 文件会话/路径接口；
  宿主安装工具。
- 进程：先做 driver→cc1/as/ld 的最小 spawn/wait/stdio 路径，按实际调用点补
  fork/pipe，不先造完整 POSIX。
- C++：先定义最小 libstdc++/异常/RTTI/TLS 范围，再构建；C 成功不等于 G++。
- Seed：固定 Canadian cross 配置；宿主工具只生成 Seed，不在宿主代执行 XOS 程序。

## 本阶段没有做的事

- 没有下载/构建 GCC 或 Binutils 源码。
- 没有修改工作盘、文件服务、内核、libc 或测试。
- 没有把宿主 `cc1` 放进镜像，也没有写假的 `open`/`fork`。
- 没有宣称 O11/O12/O13 通过；E08 仍未完成。

## 证据与下一步

- 审计 JSON：`build/e08_stage0_audit.json`
- 计划：`e08_native_toolchain_plan.md`
- 下一阶段：**E08-1 存储与文件 ABI**，先过“>128 KiB ELF 从盘上装载并运行，
  文件按路径读写、sync 后重启保留”这个 gate，再谈 binutils/GCC。
