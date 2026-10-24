# E08-4/5 用户运行时首轮分析

状态：首轮只读分析已交付；按主 agent 后续指定完成 libc C++ 入口运行时改动。未构建、未运行 QEMU，等待主端链接/loader 配套与真实探针。

范围：核对 `newlib_syscalls.cpp`、`main_entry.cpp`、`libc_runtime.hpp`、CRT/链接入口与从端交接，识别可由现有接口覆盖的需求和缺失项。此页不冻结 POSIX 扩展，也不代表任何 GCC 调用已在客体执行。

以下“现状”和从端材料记录首轮源码分析基线；后文分别记录已落地实现及后续真实运行发现。

## 观察到的现状

- `src/user/libc/main_entry.cpp` 的 POSIX `main` 入口先调用 `xos_libc_init`，随后直接调用 `main(argc, argv, environ)`，并以 newlib `exit` 结束。没有看到入口调用 `__libc_init_array` 或其它 `.init_array` 遍历器。`src/user/arch/x86_64/start.asm` 的 `XOS_POSIX_MAIN` 路径只调用 `xos_libc_main_entry`；常规 libc 路径也只初始化 XOS libc 后调用 `xos_user_main`。因此，当前代码明确没有显式的全局构造启动步骤。newlib `exit` 会执行其注册的退出处理，但目前没有显式的 `__libc_fini_array` 调用；具体 newlib 构建是否在 `exit` 内触发 fini 数组，尚未核实。
- `src/user/arch/x86_64/user.ld` 丢弃 `.eh_frame`。用户态 loader 对不支持的动态段、TLS 与重定位采取拒绝策略（`src/user/loader/elf.cpp` 注释有明确说明）。当前因此没有可供异常展开器使用的已验证 unwind section，也没有静态 TLS 映像装载/初始化路径。
- 当前自有用户态源码中未发现 `__cxa_atexit`、`__cxa_finalize`、`__cxa_guard_acquire`、`__gxx_personality_v0`、`_Unwind_*` 或 TLS ABI 的实现。`libc_runtime.hpp` 只公开 XOS libc init/finish、POSIX main entry 和 `environ`。这是对当前源码的搜索结果，不等同于对所有 newlib/GCC 归档成员的完整符号审计。
- `newlib_syscalls.cpp` 已实现真实文件访问与目录、临时文件所需的底层文件句柄；`mkstemp` 由已链接的 newlib 复用。错误映射包括 `ENOENT`、`ENOSPC`、`EBUSY` 等，不支持项有显式错误。每任务 32 个 fd 槽、每会话文件服务仍最多 8 个打开对象；这些上层槽数不会增加文件服务容量。
- 环境通过 startup v2 接入 `environ`，`getenv` 可由 newlib 依据该数组工作；`posix_spawn` 接受显式 `envp`，空指针时继承 `environ`，并对参数/环境总量作上限检查。`setenv`/`unsetenv` 没有 XOS syscall 实现点，预计由 newlib 在进程自身内存中管理环境数组；是否满足 Seed 实际需求尚未验证。
- 进程侧有 `posix_spawn`、按 PATH 搜索的 `posix_spawnp`、只接受正 PID 的阻塞 `waitpid`、文件动作（0/1/2 范围）和 pipe。`WNOHANG`、非零 spawn attributes、fork/vfork、mmap/munmap 明确失败。`execve`/`execvp` 没有在 XOS 适配源码中找到。pipe 是有限内核对象：E08 runtime 文档记载最多 8 个对象、每个 4 KiB；空 pipe 在仍有 writer 时返回 `EAGAIN`，不是完整阻塞管道语义。
- 子程序通过 XOS spawn 装载静态 ELF；这不是 Unix `fork` 后 `exec` 的实现。当前构造授权只给 supervisor 显式启动的直接 driver 子任务，普通 spawn 子任务不会获得构造权。于是 GCC driver → `collect2` → `ld` 这类可能的孙进程链需要按真实运行路线判断权限；不能据预期工具名扩大权限。

## 从端材料与证据边界

`docs/reports/e08_gcc_seed_handoff.md` 仍称 GCC 16.2.0 源码锁/哈希未完成、尚未有 Seed 客体 gate，并把 pex/fork/exec、临时文件、环境、管道与路径列为待真实调用验证的风险。当前可读 `.cache/xos_seed/gcc/gcc-16.2.0.tar.xz` 文件大小为 5.4 MiB；对它运行只读 `tar -tf` 报 `Truncated input file`，所以本轮无法从该缓存可靠追踪 GCC 16.2.0 的 `pex` 实现。报告页与缓存现状需由从端更新并校验来源哈希后再用作源码依据。

已检查 `src/user/libc/newlib_syscalls.cpp`、`src/user/libc/main_entry.cpp`、`src/user/include/xos/libc_runtime.hpp`、`src/user/arch/x86_64/start.asm`、`src/user/arch/x86_64/user.ld`、`src/user/loader/elf.cpp` 与 `docs/e08_runtime.md`。没有构建或运行客体；本报告没有产生测试结果。

## 最小实施建议

1. 先等从端交付完整、哈希已核对的 GCC 源码和构建日志，拿到其 driver/pex 的实际命令、返回码、文件路径与进程树。依据证据选择现有 `posix_spawn[p]` 路径、增加窄 libc 入口，或对上游启用既有替代实现；不先实现 fork 或任意 shell 管道。
2. 为用户 C++ host runtime 明确独立的 CRT 合同：入口遍历 `.preinit_array`/`.init_array`，正常退出运行析构与 fini 数组，并确保 newlib `atexit`/C++ `__cxa_atexit` 的终结顺序。先确认当前 newlib 已有的 exit/atexit行为和链接布局，再实现缺少的最小 glue，避免重复实现或错误次序。
3. 异常支持应保留目标文件与 ELF 中的 `.eh_frame` 等展开信息，提供实际使用的 libgcc unwinder/personality ABI，并验证异常跨函数展开时局部析构确实发生。当前 loader 支持的静态段/映射策略需核对该段是否可读；不可把只补符号或禁用异常称为已实现。
4. 全局动态构造、析构、`atexit` 与 `__cxa_guard` 可先做单任务、单线程语义；局部静态初始化需选择可工作的 guard 锁策略。TLS 单独处理：先审 GCC 生成的目标 TLS 模型、PT_TLS/静态 TLS 布局和 task startup 需求，再定最小静态 TLS 支持。当前无线程，测试只能证明任务间隔离和任务退出生命周期，不能声称线程 TLS。
5. 环境和子进程仅补真实缺项。先以 Seed 的错误日志/调用 trace 核对 `getenv`、`setenv`、PATH 查询及子工具路径；现有 startup 环境与 `posix_spawn` 可先复用。对 `collect2` 的孙进程若确实受构造权限阻止，再讨论有范围、可追踪的委托合同，不向普通任务普遍授予 builder 权。

所有以上建议均为基于当前源码边界的推断与最小工作顺序，不是已确认的 GCC 必需调用或阶段决定。后续由主端链接/loader配套和真实探针验证此次 CRT 行为，再依据具体失败点补最小 libc/SDK 实现；内核机制、loader 和构建集成仍归主 agent。

## 主 agent 指定的 CRT 增量

已增加 `src/user/libc/cpp_runtime.cpp`，并在 POSIX `main` 入口的 `xos_libc_init` 成功后、调用 `main` 前运行 `__preinit_array` 与 `__init_array`；使用 `atexit` 注册单一终结回调，该回调逆序调用 `__fini_array` 后注销已注册的 `.eh_frame`。回调在构造器执行前注册，使构造期间由 newlib 注册的 C++ 析构回调先运行。定义了单一静态映像的 `__dso_handle`，供 `-fuse-cxa-atexit` 使用。没有重定义 `atexit`、`__cxa_atexit`、`__cxa_finalize`、new/delete、RTTI 或异常实现；frame 注册/注销使用弱引用，只有两者均可用且 linker 提供 `__eh_frame_start` 时启用。

改动文件：`src/user/libc/main_entry.cpp`、`src/user/include/xos/libc_runtime.hpp`、新增 `src/user/libc/cpp_runtime.cpp`。`scripts/user_build.py` 会对 `src/user/libc/*.cpp` 建 SDK 对象，因此新文件自动进入 `libxos.a`。没有改 `start.asm`、链接脚本、loader 或 syscall 适配；主 agent 需按其安排提供数组边界及 `.eh_frame` 起始符号，并在 CRT 中先处理 TLS。未实现 `_init`/`_fini` 空钩子，也未实现 `__cxa_thread_atexit`；若从端新工具链产生这些未解析符号，应依据实际 ABI 所属/调用证据再分派，避免与 libsupc++ 重复定义。正常 `exit` 路径的 atexit 顺序是本次代码设计目标；首轮真实探针发现GCC产物使用legacy `.ctors`，因此当时未能验证全局构造/析构。

静态检查：对指定文件执行 `git diff --check`，无空白错误；源码构建、链接与客体运行均未执行。

## C++ CRT/TLS 新功能探针

按主 agent 指定新增 `src/user/programs/cpp_runtime_probe.cpp` 与 `tests/cpp_runtime_smoke.py`。客体探针通过带优先级的 preinit/init/fini section 和全局对象构造/析构输出顺序；通过 initialized TLS、零填 TLS、64 字节对齐且跨页的 TLS 数组，在两项并存的 worker 中修改并跨 yield/PIT 反复检查。worker 输出 PID/ready 与 done 标志，harness 先确认两项 worker 都 ready 且第一项未提前退出，再分别 wait 成功，检查析构先于 fini 并比较等待前后的任务/页/完成记录计数。

Harness 静态检查 ELF 的单一 `PT_TLS`，要求有初始化模板、额外零填空间、超过一页的内存尺寸及至少64字节对齐；同时将当前 probe、`cpp_runtime.cpp`、`main_entry.cpp` 源哈希绑定到 build manifest。临时512MiB FAT32盘只导入该探针。主 agent 已将其纳入 `disk_programs`/`libc_programs`，使用 `crt0_posix`、`-fuse-cxa-atexit`、`-ftls-model=local-exec`；内核 TLS 初始化/FSbase由主端实现。

当前交付文件为 `src/user/programs/cpp_runtime_probe.cpp`、`tests/cpp_runtime_smoke.py` 与本交接页。Python AST 解析和指定文件静态空白检查通过；没有运行 harness、构建或 QEMU。主 agent 将串行执行 build 和 `tests/cpp_runtime_smoke.py`，观察真实初始化/析构顺序、两个并行进程的 TLS 隔离及资源归零。若不通过，由实际串口失败标记或错误返回定位，不扩展为压力测试。

## GCC legacy constructor list 修复

主端首轮运行 `cpp_runtime_smoke` 时，实际串口显示 preinit/init 和 TLS ready 成功，但缺少 global constructor；对客体 ELF 的 objdump 检查确认 x86_64-elf GCC 把该构造器放入 `.ctors`。主端保留失败证据于 `build/cpp_runtime_smoke_report.json`，该轮不得记为通过。

已在 `cpp_runtime.cpp` 增加弱边界 `__ctors_start/end` 与 `__dtors_start/end`。初始化顺序现在为 preinit → init_array 正序 → legacy ctors 逆序；正常终结回调先 legacy dtors 正序，再 fini_array 逆序，最后 deregister frame。legacy 表项过滤空指针与全 1 sentinel；现代数组逻辑保留。主端负责链接脚本按普通 `.ctors`/`.dtors` 在前、带优先级 section 排序在后的布局。

本次只做静态编辑，未重新构建或运行 probe；需要主端重新串行执行新功能验收，确认 ctor/dtor 次序及 TLS/resource 结论。若工具链改为仅现代数组，该兼容路径仍可通过弱符号缺省跳过。
