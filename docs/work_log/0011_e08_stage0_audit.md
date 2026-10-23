# 0011：E08-0 审计，不先搬 GCC

日期：2026-10-23（Asia/Shanghai）。状态：E08-0 完成审计；E08-1 未开始。

## 范围

用户要求先拆分 E08，随后只做阶段 0。本组只做审计：固定版本、实测宿主/目标
工具链大小与格式、记录当前 XOS 盘/文件/进程上限和缺口。没有下载或构建 GCC，
没有改内核、文件服务、libc、测试或工作盘。

## 固定与测量

- GCC/G++ 16.2.0（target x86_64-elf）、Binutils 2.47、newlib 4.6.0.20260123、
  QEMU 11.1.2 / 64 MiB。
- `cc1` 40,163,440 字节、`cc1plus` 42,714,480 字节，均为 Mach-O arm64；
  GCC 安装树 201,359,486 字节。
- GCC 源码包 107,200,820 字节；Binutils 源码包 29,034,716 字节。
- newlib 预构建 10 MiB；当前工作盘 16 MiB；文件 4×24,576 字节；
  64 用户页/任务、8 任务；启动镜像上限 512 KiB。
- `libstdc++.a`、`libgcc_eh.a` 不存在。

## 结论

当前不能直接开始原生 GCC：

1. 宿主 cc1/cc1plus 是 arm64 Mach-O，不能在 x86_64 XOS 执行；需 Canadian cross。
2. 40 MiB 级编译器与 16 MiB 盘/256 KiB 进程上限差一个数量级。
3. 子程序没有 per-process 文件会话/路径；libc `open/stat/unlink` 为 ENOSYS。
4. 没有 fork/exec/waitpid/pipe/环境变量，GCC driver 无法启动子工具。
5. 没有 libstdc++/libgcc_eh，C++ 异常/RTTI/TLS 尚不可链接。
6. 宿主动态依赖 libiconv/MPC/MPFR/GMP/zlib/zstd/libc++，不能混入 sysroot。

所以 E08-1 暂停，先做“更大工作盘 + 流式文件 + per-process 文件会话 + 宿主安装”
的存储/文件 gate。E08 未完成，O11–O13 仍不标通过。

## 证据

- `scripts/e08_stage0_audit.py`
- `build/e08_stage0_audit.json`
- `docs/e08_stage0_audit.md`
- `docs/e08_native_toolchain_plan.md`

### 追加：E08-pre1 完成

`docs/e08_pre1_design.md` 已冻结为基线：512 MiB RAM、2 GiB FAT32、65536 用户
页、8 任务、per-task 文件会话、流式段装载、posix_spawn 优先、C++ 范围
（前端/libstdc++ 基础/异常/RTTI/TLS；iostream 可选）。机器可读决定在
`config/e08_pre1_baseline.json`。这是规划基线，不是当前已实现值；仍然没有
实现、没有改代码或测试。E08-1 未开始。

没有构建/测试变更；当前 65 组回归和构建 ID 不受本组影响。
E08-1 未开始，等待范围/预算确认。
