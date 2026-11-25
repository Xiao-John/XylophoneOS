# glibc G2/G3 接管审计与验收交接

2026-11-25。审计基线为最新 main 5e49012ab2b359b31999d78083341ede98d5de4f 加 #142/#148 的 G1 候选恢复，集成提交 6a463517bfa0d4d183c9107578c0ce582d6ed2d1（PR #149）。本记录区分已存在的对象/桥接证据与 G2/G3 真正需要的 libc 客体证据。

## 当前接手入口（同日后续交付）

| 范围 | 后续交付及证据范围 |
|---|---|
| G1 桥接与历史 | [#149](https://github.com/Xiao-John/XylophoneOS/pull/149) 保留 #142/#148 的历史和实际集成树。G1 桥探针的运行范围以各次链接对象为准。 |
| G2 静态纵切片 | [#151](https://github.com/Xiao-John/XylophoneOS/pull/151) 提交完整静态候选 SDK、CRT、主线程 TLS/errno 与公共 API 的 6 次客体运行。 |
| G3-T 私有线程 | [#152](https://github.com/Xiao-John/XylophoneOS/pull/152) 提交公开 pthread、私有同步、静态 TLS 和线程生命周期的目标验收。 |
| G3-F 文件服务 | [#153](https://github.com/Xiao-John/XylophoneOS/pull/153) 提交静态 glibc FD/stdio、接收端继承、服务死亡与资源回收证据。出站 fork/exec 另行处理。 |
| 源码认证 | [#154](https://github.com/Xiao-John/XylophoneOS/pull/154) 提交独立签名信任材料及构建准入检查，旧候选认证结论仍只适用于旧锁。 |

独立 PR 的结果绑定各自源码、SDK 和系统。以实际整合输入重新构建并执行受影响的客体 gate 后，再登记组合资格。以下为最初交接时的事实和未运行记录。

## 原始执行环境预检

当前执行容器没有挂载 XylophoneOS 工作树。工具预检结果：

| 工具 | 结果 |
|---|---|
| x86_64-elf-gcc / x86_64-elf-g++ | NOT_FOUND |
| x86_64-elf-readelf | NOT_FOUND |
| NASM | NOT_FOUND |
| QEMU x86-64 | NOT_FOUND |
| GNU make | 仅系统 /usr/bin/make，未找到锁定隔离的 gnumake |
| gawk / bison | NOT_FOUND |
| gpgv | /usr/bin/gpgv 可用 |

因此本次没有声称重新构建 glibc、生成 gnu/stubs.h、构建 SDK 或运行 XOS 客体。此前工作记录中的哈希与客体结果保持其原有源码/镜像范围，不重绑到当前 main。

## 原始 G1 证据

- #142 提供 glibc 2.44 的 XOS sysdeps 候选、隔离构建探针、目标对象/依赖来源核对和若干真实 XOS 客体桥探针。
- #148 增补 brk、匿名 VM、随机数、静态 DTV、pthread 创建/退出/身份/调度/名称/信号及命名对象失败语义。
- 既有客体桥多轮资源恢复通过，覆盖的是其实际链接的 XOS 原生桥对象；并未启动完整 glibc CRT、glibc TLS 主线程初始化或完整 pthread 程序。
- #148 记录的最后完整构建阻塞为 nptl/syscall_cancel.o 缺少构建规则；正式 gnu/stubs.h、完整 libc、匹配 SDK 尚未生成。
- src/ports/glibc/source_lock.json 仍为 candidate_unverified_signature。归档 SHA-256 为 37f600f2bef3c5e8300147059568b2a2e40a7ad6ccc65ce942556d49429cc667。工作记录中有 keyserver 公钥的密码学验证，但更新密钥、撤销状态及签名者身份尚未通过独立可信渠道确认；发行输入继续禁止使用。

## 原始 G2 静态纵切片缺口

G2 必须由真实 glibc 静态程序启动，而不是把 glibc 单个对象与原生测试桥链接。

| 能力 | 当前代码/证据 | G2 尚缺 |
|---|---|---|
| 目标 CRT 与入口 | XOS _exit 对象已编译；部分桥探针由既有 XOS loader/CRT 启动 | glibc 自己的 _start、__libc_start_main、启动栈/argv/env、初始化顺序的实际静态程序运行 |
| 主线程 TLS/errno | x86-64 NPTL 布局和静态 DTV 对象已构建；TLS_INIT_TP 候选仍显式失败 | 在真实 XOS 主线程安装 FS/TP；验证 errno、TCB、DTV、TLS 模板和失败回滚 |
| 堆与 VM | brk/mmap/mprotect/munmap 对象及独立客体探针已有历史结果 | glibc malloc/free 在 glibc 自身 TLS/errno 与真实启动下运行；分配失败、碎片、回收和边界 |
| stdio | 若干头文件和 _exit 对象检查 | glibc printf/fprintf/fopen/fclose 实际工作；短读写、EOF、错误映射、flush 与退出收尾 |
| 错误路径 | 候选 errno 表、时钟/随机数等对象模拟和部分客体探针 | 对真实 libc 客体验证 errno 保持/更新、坏指针、资源耗尽及服务错误 |

因此 G2 目前被完整构建与主线程 TLS 初始化双重阻塞。

## 原始 G3 纵切片缺口

### 线程/TLS/同步

已存在实验性 pthread_create、join/detach、线程名称、线程身份和静态 DTV 代码。仍需证明：

1. 主线程先正确建立 glibc TCB/FS；随后由公开 pthread_create 创建线程，而非仅由测试桥直接调用原生线程 reservation。
2. 两个线程并发访问 libc，errno、TLS、TSD、C++ thread_local 析构和 glibc 内部状态相互隔离。
3. mutex/cond/once/sem 的实际消费者路径。当前 low-level futex 适配器只允许 private、untimed wait/wake；timed、shared、requeue、PI、取消路径会显式 trap 或失败。
4. 取消接口 __syscall_cancel 当前返回 ENOSYS，__syscall_do_cancel trap；不能声称 POSIX cancellation 已支持。
5. 线程退出、join/detach 竞态、最后线程退出、进程退出/异常、资源回收必须在完整 glibc 程序下验证。

### 文件/FD

现有 glibc XOS sysdeps 还没有完整文件系统调用纵切片。当前目录中可见 fd_to_filename、dirstream.h、标准 FD 安全检查等辅助项，但尚未提供完整的 open/read/write/close/lseek/fstat 等文件后端与 XOS files 服务客户端的组合。标准 FD 安全检查目前选择 fail-closed 退出路径。

G3 文件 gate 至少要覆盖：
- glibc FD 创建/关闭、偏移、短读写、EOF、错误码及 errno；
- 多线程并发读写和同一 open-description 的偏移序列化；
- XOS 文件服务请求/响应序列的线程安全，避免不同线程取走彼此回复；
- 服务死亡、端点关闭、超时和失败回滚；
- spawn/fork/exec 中 FD 继承与 close-on-exec 的真实客体行为；
- 退出时 FD/服务端句柄回收与资源回基线。

## 原始分阶段交付门

| 里程碑 | 可提交条件 | 当前状态 |
|---|---|---|
| G1 主线整合 | #142/#148 与最新 main 三方整合，保留历史、无文件内容冲突 | 已作为 PR #149 提交；待合并 |
| G1 构建收口 | 锁定工具和源码可复现；完整构建首错处理；生成真实 stubs/sysroot | NOT_RUN / blocked |
| G2 | glibc 自己的静态 ELF 在 XOS 客体运行，入口、TLS/errno、malloc/free、stdio、错误与退出通过 | NOT_RUN |
| G3-T | 完整 glibc 程序使用公开 pthread API；TLS/errno 隔离、同步、线程退出/回收通过 | NOT_RUN |
| G3-F | glibc 文件/FD 后端对接 XOS files 服务；并发、故障、继承和资源恢复通过 | NOT_RUN |

## 原始重放命令与环境要求

先安装仓库 config/toolchain.json 锁定的目标工具链和隔离 GNU 构建工具，再准备与 source_lock.json 完全匹配的 glibc 2.44 归档及独立可信的签名者身份/密钥证据。随后从全新输出目录重跑：

```sh
python3 scripts/glibc_g1_probe.py --archive "$GLIBC_ARCHIVE" --output build/glibc_g1_mainline --xos-backend
python3 tests/glibc_g1_artifact_test.py build/glibc_g1_mainline --archive "$GLIBC_ARCHIVE"
python3 tests/glibc_g1_bridge_guest.py --entry-build build/glibc_g1_mainline --exit-build build/glibc_g1_mainline --identity-build build/glibc_g1_mainline --memory-build build/glibc_g1_mainline
```

以上只重放 G1 已有探针；不能据此报告 G2/G3。完整构建修复后另建 glibc SDK 和静态消费者 ELF，再新增独立 G2 客体报告。G3-T/G3-F 分开实现、分别提交 PR，避免把线程同步和文件服务耦合成一个不可审阅的大改动。

## 原始审计结论

本次已完成远端基线整合与源码/契约审计；G2/G3 尚未取得实现和客体资格。当前容器缺少目标交叉编译器、目标 binutils、NASM、QEMU、gawk、bison 与隔离 gnumake，无法执行完整验收。后续 PR 将继续按模块提交，并在每个 PR 中保留精确的 PASS/FAIL/NOT_RUN 证据。
