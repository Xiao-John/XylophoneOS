# E06：newlib 与用户态 C 运行库

实施于 0010。目标不是“完整 POSIX 系统”，而是让实际 SDK 程序可以用 C 库的
常用部分，并留下从真实配置/产物得到的依赖清单。E08 才移植原生 GCC/G++。

## 结论

- 选择的 libc：**newlib 4.6.0.20260123**，target `x86_64-elf`，静态链接。
- 已跑通：`printf`、`puts`、`malloc/free`、`strcpy` 等 string 函数、返回码/退出。
- 已提供 C 控制台 read/write、静态 64 KiB `sbrk` 堆、errno 基本映射。
- 已启用 per-task SSE/x87 状态（FXSAVE/FXRSTOR）；newlib 的 x86-64 ABI 使用
  SSE 寄存器，不能靠“禁用 SSE”可靠运行。
- 没有 libstdc++、异常/RTTI、TLS、线程、动态链接、C++ 静态构造初始化。
- `fopen`/POSIX 路径尚未映射到 XOS 文件服务；`open`/`stat`/`unlink` 返回 ENOSYS。

## SDK 与链接

`build/sdk/` 现在包含：

- newlib 头（`include/`）；
- `lib/libc.a`（6,720,094 字节，SHA-256
  `283fa07ad205c80af92e955a91da027435d8a8a90cb7e27933f57925cc5baa22`）；
- `lib/libm.a`（2,701,158 字节）；
- `xos` 头、CRT、`libxos.a`、`libxos_loader.a`、`user.ld`；
- `COPYING.NEWLIB` 与 SDK `manifest.json` 中的 libc 版本/哈希。

`scripts/user_build.py` 的 `libc_programs` 列表决定哪些程序链接 newlib。
当前只有 `libc_hello`；其他旧程序保持窄 SDK，避免内核镜像无谓膨胀。新增
libc 程序时同时加入 `names` 与 `libc_programs`。

示例 `src/user/programs/libc_hello.cpp`：

```cpp
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern "C" int xos_user_main(const xos::startup_info*) {
    char* text = static_cast<char*>(malloc(32));
    strcpy(text, "malloc+printf");
    printf("libc says: %s %d %x\n", text, 42, 0xbeef);
    free(text);
    puts("second line");
    return 7;
}
```

程序在 `sup> exec libc_hello` 下输出两行并返回 7；第二次运行也通过，
说明 stdio/heap 没有在第一次退出后留下坏状态。实际截图见
`build/libc_screen.png`。

## 运行库适配层

`src/user/libc/newlib_syscalls.cpp` 提供 newlib 需要的系统接口：

- `_write` / `write`：stdout/stderr 走 XOS handle write，按 256 字节分块。
- `_read` / `read`：当前是单字节非阻塞控制台；空状态映射为 EAGAIN。
- `_sbrk` / `sbrk`：进程私有静态 64 KiB 堆，越界返回 ENOMEM；不是内核 brk。
- `_close`、`_fstat`（字符设备）、`_isatty`、`_lseek`、`_exit`、`_getpid`、
  `_kill`、`_times`。
- `open`/`stat`/`unlink` stub 返回 ENOSYS，明确不把宿主路径或 XOS 文件服务
  伪装成 POSIX 文件系统。

## SSE/x87 上下文

E06 必须在 E04 的整数型任务上增加浮点状态，否则 newlib 的 `malloc` 等代码
一执行 SSE 就会 #UD。实现：

- `CR0.EM/TS` 清除，`CR4.OSFXSR/OSXMMEXCPT` 置位，`fninit`，MXCSR 默认 0x1F80。
- 每个 `task_record` 有 16 字节对齐的 512 字节 FXSAVE 区；任务切换前
  `fxsave64`，切入后 `fxrstor64`。内核代码仍 `-mgeneral-regs-only`，不把
  XMM 状态带进内核 C++。
- E04 的 `fault fpu` 探针因此不再 #UD；E04 回归改为验证它正常退出 99。
  这不是“FPU 故障测试失效”，而是 E06 正式支持了 FPU 上下文。

## 实际依赖清单

`python3 scripts/libc_audit.py` 从 `build/sdk` 与 `libc.a` 实际产物生成
`build/libc_audit.json`。关键项：

- newlib `libc.a`/`libm.a` 哈希与字节数来自实际文件，不是手填版本号。
- libc 对象引用的控制台/堆符号由 `libxos.a` 的适配层提供；`open`/`stat`/`unlink`
  被显式列为 unsupported，而不是假装成功。
- `libc_hello.image.elf` 66,664 字节，BSS 约 66 KiB（含 64 KiB 堆），
  用户页 40 页；在 64 页上限内。
- `libc.a` 中仍有大量未解析符号（约 1037 个，含 libm/可选函数）；只有实际
  被链接对象才需要解析，不能把“libc.a 很大”当成完整实现证明。

## 构建可复现性

`src/third_party/newlib/` 保存预构建的 `x86_64-elf` 头与 `libc.a`/`libm.a`
以及 `COPYING.NEWLIB`；`README.md` 和 `scripts/build_newlib.sh` 记录从
`sourceware.org` 下载 4.6.0.20260123、configure 与编译的路径。普通
`make build` 不联网、不重建 newlib，只把已存在的预构建包复制进 SDK。
重新生成时须重新记录哈希，不能默认版本相同即二进制相同。

## 验证与边界

`make smoke` 新增 E06 3 项：库程序进入 image catalog、printf/malloc/string/
退出 7、第二次运行可复用；E01–E07 旧 62 项继续通过（合计 65）。

未实现/不声称：完整 POSIX、目录/路径、`fopen`、文件服务 POSIX 映射、libstdc++、
C++ 异常/RTTI、TLS、线程、动态链接、C++ 静态构造、跨进程 malloc 共享、
真实掉电下的库缓冲一致性。E08 才把 GCC/G++ 搬进 XOS。
