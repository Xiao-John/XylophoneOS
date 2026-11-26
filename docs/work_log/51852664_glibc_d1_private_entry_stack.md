# 51852664 · glibc D1 原生启动栈交接

2026-11-26 · 主线基线 `4089796a`，探针源码 `4865661a`。本轮完成 bootstrap 到 x86-64 glibc 的进程内启动栈构造，使用现有 startup v1/v2/v3 的参数和环境投影。完整解释器启动、原生加载描述及文件会话交接仍待实现。 [D0 契约](../contracts/dynamic_linking_d0.md#52-入口auxv-与文件会话)

## 固定的上游交接

| 上游 glibc 2.44 位置 | 原生实现所需条件 |
| --- | --- |
| `sysdeps/x86_64/dl-machine.h:136` 的 `RTLD_START` | 入口 `%rsp` 16 字节对齐，指向 `argc`，随后是带 NULL 结尾的 `argv`、带 NULL 结尾的 `envp` 和以 `AT_NULL` 结尾的 auxv。入口将同一地址传给 `_dl_start`。参照 `src/ports/glibc/crt/start.c` 的静态转换，但保留动态入口额外的 `argc` 栈字与地址项。 |
| `elf/rtld.c:516` 的 `_dl_start` | 根据解释器自身的 `__ehdr_start` 和 `_DYNAMIC` 定位并自重定位，随后进入 `_dl_start_final`。`AT_BASE` 应与实际解释器装载偏移对应，自重定位过程不靠它定位自身。 |
| `elf/rtld.c:494` 与 `sysdeps/generic/ldsodefs.h:1164` | `_dl_sysdep_start` 按受检的栈和 XOS 启动状态设置 `_dl_argc`、`_dl_argv`、`_environ`、`GLRO(dl_auxv)`、`__libc_stack_end`、页面大小、随机源和 secure 状态。它须让文件及环境访问可用，再调用 `dl_main(phdr, phnum, &entry, auxv)`。CPU feature 和排序初始化需按上游顺序核对。 |
| `elf/rtld.c:1085` 的 `rtld_setup_main_map` | `AT_PHDR` 指向 main 的实际表。`PT_PHDR` 给出 PIE 偏移并须早于使用该偏移的 `PT_LOAD`、`PT_DYNAMIC` 与 `PT_INTERP`。`AT_ENTRY` 指向实际 main RX 入口；它不能与解释器入口相等，否则上游走直接执行解释器的模式。 |
| `sysdeps/x86_64/dl-machine.h:144` 与 `sysdeps/x86_64/start.S` | `_dl_start_user` 复用原始栈读取参数和环境，运行初始化后恢复该栈，再跳到 main ELF 的入口并将 `_dl_fini` 放在 `%rdx`。`AT_RANDOM` 指向活的可写存储，glibc 启动使用后清理它。 |

`src/user/loader/glibc_d1/entry_stack.cpp` 读取现有有界文本区，要求 argv/env 表在映射内且有终止项，拒绝送入 glibc 的 `LD_*` 和 `GLIBC_TUNABLES`。原生环境白名单及授权由受信启动方另行完成。启动栈借用现有可写 startup 文本并保持其生命周期。构造器检查高地址入口位于文件支持的 RX LOAD，main PHDR 表与文件偏移吻合并落在同一可读 LOAD 内，解释器的文件头对应偏移零。不同映像的保留范围不重叠。调用方带入已经验证的 ELF 描述和经策略判定的 secure 状态；候选构造器在任何检查或熵调用失败时保留原目标字节。当前预算为 64 个参数、64 个环境项和至多 64 个 PHDR，待实际动态闭包测量后再冻结。

## 原生状态的两个接续方案

1. 保留上游 `RTLD_START`，由受信 bootstrap 在初始栈之外固定一个受限只读的进程内描述区。用经评审的私有指示方式交给 `_dl_sysdep_start`，并按版本、范围、图和引用生命周期验证。此方案复用现有栈入口和 `_dl_start_user`。需要另行确定启动方如何用现有 owned constructing 地址空间与已认证 IPC 将真实 pin、继承 FD、cwd 和服务会话交给 bootstrap，以及描述位置如何稳定发现。内存描述本身只表达事实，句柄权利来自现有内核和 files 服务。
2. 为 XOS 实现私有 `RTLD_START` 入口，把现有 glibc 栈与独立原生描述指针作为不同参数。入口需在自重定位前用无需 GOT 的方式保存描述，并显式传递到 `_dl_sysdep_start`。此方案能明确区分进程内结构及引用生命周期，代价是新增 x86 汇编、上游参数适配和回归范围。main 端的 `%rsp`/`%rdx` 交接仍须保留。

两条路线都需要可独立验证的早期 I/O。静态 `xos_file_runtime.c` 根据 `__xos_startup` 初始化描述符，会话接续须保住请求序列与结果未知处理。早期 rtld 尚无该 TLS 与运行时状态。Linux `dl-sysdep.c` 使用的 `brk` 探测、secure FD 修补及环境策略需要逐项对应 XOS 原生行为。下一步须先确定并验证受限的早期文件状态及移交方式，再去掉 XOS `dl-sysdep.c` 的共享编译保护。当前工作未登记新的 wire 字段、额外 auxv 项或解释器入口协议。

## 可重放的试验

从同一个 GCC PIC 对象 `int fixture_entry(void) { return 19; }` 分别用 GNU `ld -pie --dynamic-linker /usr/lib/xos/glibc_dynamic_v1/ld_xos_x86_64.so.1` 和 `ld -shared` 生成测试输入，入口 `fixture_entry`，链接选项含 `-z noexecstack --build-id=none`。真实 PIE 的 `PT_PHDR` 位于第一个可读 LOAD 的 `0x40`，表项数为 6。两个映像以 `0x100000200000` 与 `0x180040000000` 同时映射。探针复制 ELF LOAD 后落实 RX/RW 页并实际通过栈中地址读取高地址 PHDR 和解释器测试文件头。栈切换后由测试入口读回数据，全程未运行任一高地址输入的入口。

宿主在 x86-64 Linux 上用 `g++ -O2 -std=c++20 -Wall -Wextra -Werror -fsanitize=undefined -fno-sanitize-recover=all` 编译构造器和 `tests/fixtures/glibc_d1/entry_stack_host.cpp`，包括 `src/shared/include`、`src/user/include` 和 `src/user/loader/glibc_d1`。执行时以 PIE 和 DSO 文件路径为参数。通过三种 native startup 文本投影、三次实际 `%rsp` 切换、64+64 满容量和 11 项拒绝检查。拒绝路径检查目标字节不变，熵失败包含供应方已写入临时缓冲的情形。

XOS 复跑用同一源码并加 `--define D1_NATIVE_GUEST`，以 `scripts/build_glibc_program.py --cxx` 链接到先前已验签及校验工件的静态 C++ SDK，再通过 `exec-file /bin/handoff_probe /bin/main-pie /bin/interpreter-fixture` 运行。使用历史 D1-C 已验证 ISO `fa9ab7324b44240e`，QEMU 11.1.3 单 CPU、512 MiB、无网络及临时 FAT 工作盘。实际读到 launcher 的 v2 startup 与 PATH，从 `getrandom` 走 XOS sys63 获取 16 字节，在本进程启动栈切换后验证字节与写入能力，正常退出 0。前后空闲页、任务及完成记录均为 `129711 / 3 / 1`。使用同一 SDK 的 GCC 16.2.0 还以 `-ffreestanding -fPIC -mno-red-zone -fno-exceptions -fno-rtti -fno-stack-protector` 生成实际 x86-64 ET_REL 构造器，`nm -u` 为空。本轮资格止于静态客体中的私有栈和地址数据读回，glibc `ld.so`、构造函数、动态 TLS、启动 ready 及新 SDK 组合仍待验收。

| 工件 | SHA-256 |
| --- | --- |
| 历史系统 manifest | `ce356ec78ba39744ee936a7c6a6022c9ce20e88bb902b5b386f3e33ec76e13f2` |
| 历史系统 ISO | `7959f863faecfec73657659ee28ec2b2571c2baad710e24b4ee782ab2478953c` |
| 已验签静态 glibc C++ SDK manifest | `a4a6b3c278e34773088b11bb2a352d96487b9234755b9fcb9c7fe96ab9ace96e` |
| `build/handoff-evidence/guest-profile.json` | `a16f9c9cfda8dc75b801f178436574ac54d66c30058c3d294d7518ccd6803715` |
| `build/handoff-evidence/main-pie.elf` | `1c306f191b23c0469f1c5cddd025325939b7a04a8b923da12425d1c6596cf89d` |
| `build/handoff-evidence/interpreter-fixture.so` | `748ca62d9677bc07c66c011261da618d364b91f872194cee30f232130a00947a` |
| `build/handoff-evidence/entry-stack-final.elf` | `b6ee71073a72d86927260f31da1eef737d6711c5693e59a8da0ac828aa60def5` |
| `build/handoff-evidence/host.log` | `bf98d08b795560b0896f8d17bffff6aa9136fb1fa1207a1b6a2de327c0ac1127` |
| `build/handoff-evidence/guest-report.json` | `8cbb3ac0556fef332d6e2abb54c0145a24e197e372d20eecde0792bc125d18e1` |
| `build/handoff-evidence/entry_stack_serial.log` | `80de1a4b0a0abf520c3247abbe9bdb3a907c1d162c46e795acf8a6faf7447e2a` |
| `build/handoff-evidence/entry-stack-final.elf.build/manifest.json` | `6e3a23d16a5abc1f344f45155ec6867825f12f0db416f225825ea9a0084c7b76` |
| `build/handoff-evidence/entry-stack-freestanding.o` | `9a5983fe65195ffaa85c67c3cf00ba896a525a0c8c55a67c72e5521f4cdd7038` |
