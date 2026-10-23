# 0010：把 newlib 真正搬进来，而不是挂个名字

日期：2026-10-23（Asia/Shanghai）。负责：主 agent。状态：E06 本版完成。

## 范围与结果

按用户顺序 E05 → E07 → E06，本组做 E06：审计实际运行依赖、选择 libc 并让首批
工具真正运行。结论是 **newlib 4.6.0.20260123 / x86_64-elf**，不是“完整 POSIX”。

完成：

- 在独立前缀构建/安装 newlib，预构建 `libc.a`、`libm.a` 与头文件放入
  `src/third_party/newlib/x86_64-elf/`；`make build` 不联网、不重建。
- `build/sdk/` 导出 newlib 头、`libc.a`、`libm.a`、`COPYING.NEWLIB`；
  SDK manifest 记录版本和实际哈希。
- 新增 `src/user/libc/newlib_syscalls.cpp`：控制台 read/write、字符设备 fstat/
  isatty、64 KiB 静态 sbrk 堆、close/lseek/exit/getpid/kill/times、errno。
  `open/stat/unlink` 明确返回 ENOSYS，不伪装 POSIX 路径。
- `libc_programs` 显式列出链接 newlib 的程序；新增 `libc_hello`，使用
  `printf`、`malloc/free`、`strcpy`、`puts`，退出 7。
- newlib x86-64 ABI 使用 SSE；新增每任务 FXSAVE/FXRSTOR 上下文（512 字节，
  16 字节对齐），CR0.EM/TS 清除、CR4.OSFXSR/OSXMMEXCPT、MXCSR 0x1F80。
  内核仍 `-mgeneral-regs-only`，不把 XMM 带进内核 C++。
- 用户 ELF 文件上限从 64 KiB 扩到 128 KiB（实际 libc_hello 66,664 字节），
  内核镜像读取/装载缓冲同步扩到 128 KiB。
- E04 的 `fault fpu` 从“未支持 FPU 故障”改为“FPU 正常退出 99”；
  旧 SDK 仍由测试检查不含 XMM/x87 指令。
- 新增 `scripts/libc_audit.py` 与 `make libc-audit`，从实际
  `libc.a`/`libm.a`/`libc_hello` 生成依赖清单。

## 文件

新增：

- `src/user/libc/newlib_syscalls.cpp`。
- `src/user/programs/libc_hello.cpp`。
- `src/third_party/newlib/`（prebuilt include/lib、`COPYING.NEWLIB`、README）。
- `scripts/build_newlib.sh`、`scripts/libc_audit.py`。
- `tests/libc_smoke.py`、`docs/e06_libc.md`。

修改：

- `scripts/user_build.py`：SDK 复制 newlib、`libc_programs`、链接
  `--start-group libxos -lc -lm -lgcc`、128 KiB 模块上限。
- `src/user/loader/load.cpp`：装载缓冲 128 KiB。
- `src/kernel/arch/x86_64/tasks.cpp`：FPU 初始化、FXSAVE/FXRSTOR、任务状态。
- `src/kernel/arch/x86_64/tasks.cpp` 的 image read 上限 128 KiB。
- `tests/process_smoke.py`：FPU 新语义；旧 SDK 仍检查无 FP/SIMD。
- `Makefile`：`libc-audit`、`libc_smoke`。
- `docs/e04_loader_sdk.md`、README/state/toolchain/usage/friend quickstart。

没有修改 `localpilot/`；没有创建并行 agent；没有并发构建。

## 关键选择

- newlib 而不是 musl：newlib 有 `x86_64-elf` 目标与可配置的小型 libc；musl 更
  贴 Linux syscall，首轮移植成本更高。newlib 只是候选变实际，不等于完整 POSIX。
- 预构建 + 记录：`make build` 不依赖网络/2 分钟构建；`scripts/build_newlib.sh`
  保留可复现路径，实际哈希写入 audit/SDK manifest。
- 静态 64 KiB 堆：没有用户态 brk/mmap syscall；`_sbrk` 用进程私有 BSS 堆，
  失败返回 ENOMEM。不是通用虚拟内存分配器。
- SSE 上下文：newlib 的 x86-64 ABI/生成代码使用 SSE，不能靠 `-mno-sse`
  绕过（libc 的 double 路径会 “SSE register return with SSE disabled”）。
- 只让 `libc_programs` 链接 newlib，避免旧 SDK/内核镜像无谓膨胀。
- `open/stat/unlink` 不接 XOS 文件服务：子程序没有文件服务端点；先明确
  ENOSYS，不把文件系统存在误报成 POSIX 文件 I/O。

## 环境、产物与证据

宿主 macOS 27.0.1 / Apple Silicon；GCC/G++ 16.2.0、Binutils 2.47.20260726、
NASM 3.02、QEMU 11.1.2；newlib 4.6.0.20260123。

```text
PASS: 6 checks | build b22ab24c090981b2
PASS: 18 E02 checks | build b22ab24c090981b2
PASS: 12 E03 checks | build b22ab24c090981b2
PASS: 13 E04 checks | build b22ab24c090981b2
PASS: 8 E05 checks | build b22ab24c090981b2
PASS: 4 E07 checks | build b22ab24c090981b2
PASS: 1 E07-full check | build b22ab24c090981b2
PASS: 3 E06 checks | build b22ab24c090981b2
```

合计 65 组；构建 ID `b22ab24c090981b2`；源码摘要
`b22ab24c090981b273de502e106dfc40c9ae0a9b94be2d155928d9f1dcf7d973`。

| 产物 | 字节 | SHA-256 |
|---|---|---|
| `kernel.elf` | 734720 | `85f5a3d68e2af5375ceb88e97708bb8061c240b6d56ea6cf26021bf43bab2b45` |
| `kernel.bin` | 262164 | `da8c8ead758dcf6af6f56d14c00a045bdbbbe2ca51116246b6b46636ef906a98` |
| `xos.img` | 1474560 | `93ce8fb6c6ef6b28dce6a6f758d7854588d707159c2374dfcb5be7e5f9825e43` |
| `real_mode.img` | 1474560 | `8b7268b771158dc41f21e5928ad4b33067cf4a5b1de439d9554852b2ac769c72` |
| `user_libc_hello.image.elf` | 66664 | `6801e6c67c1d5ee88677dbee27a90c9f68c6fcaca5275e99407264c72c645030` |
| `sdk/lib/libc.a` | 6720094 | `283fa07ad205c80af92e955a91da027435d8a8a90cb7e27933f57925cc5baa22` |

内核 513 扇区，内存范围 0x100000–0x153000；`libc_hello` 40 用户页，在 64 页
上限内。`build/libc_audit.json` 记录实际 libc/libm 哈希、适配符号、未解析数量。
实际 VGA：`build/libc_screen.png`，已查看。

## 验证

| 检查 | 结果 |
|---|---|
| image catalog | `image=libc_hello` 出现 |
| printf/malloc/string/exit | 输出 `libc says: malloc+printf 42 beef`、`second line`，exited 7 |
| 第二次运行 | 仍 exited 7，stdio/heap 可复用 |
| 旧回归 | E01–E07 62 项通过，合计 65 |

## 失败与修正

- 首次运行 #UD vector 6：newlib `malloc` 使用 XMM；先在 E04 的整数任务上跑，
  必然失败。改为启用 SSE/FPU + FXSAVE/FXRSTOR，而不是关闭 SSE。
- 用户 ELF 66,664 > 64 KiB：`sys_image_read` 上限和装载缓冲仍是 64 KiB，报
  `error=-2`。统一扩到 131072，并同步测试/文档。
- newlib 与 `libxos.a` 的链接顺序：先扫 `libxos` 后扫 libc 会留下 `_exit/
  getpid/kill` 未解析；用 `--start-group` 包住两个 archive。
- newlib 头触发 `-Wshadow`；适配层/库程序单独 `-w`，不关闭其他源码的严格警告。
- E04 的 `fault fpu` 预期不再成立：更新为正常退出 99，并保留旧 SDK 无 FP/SIMD
  的静态检查。

## 未实现与边界

- 没有完整 POSIX、`fopen`/路径、目录、文件服务到 libc 的映射；`open/stat/unlink`
  返回 ENOSYS。
- 没有 libstdc++、C++ 异常/RTTI、TLS、线程、动态链接或 C++ 静态构造。
- 64 KiB 进程私有静态堆；不是内核 brk/mmap，不是通用虚拟内存。
- newlib 预构建包约 10 MiB；重新生成需网络和工具链，普通 build 不联网。
- 未做长时间 malloc/stdio 压力、浮点异常语义、跨任务共享堆、掉电库缓冲一致性。
  E08 才移植原生 GCC/G++；E09 才做完整试用。

## 下一步

E08：交叉构建并移植原生 GCC/G++ 及所需工具，让 XOS 内编译多文件 C/C++ 并由
XOS 执行。E06 的 libc 依赖清单和 `libc_hello` 作为其输入，而不是最终验收。
