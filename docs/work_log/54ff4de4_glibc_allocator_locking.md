# 54ff4de4 · glibc 多线程分配器加锁

独立源码基线为 `9f7a9a0f791700d15eac60ee03e455948546ce32`。此增量修改 XOS
glibc 的内部头文件选择。核对了锁定源 glibc 2.44、XOS 线程实现和历史普通静态 ELF。

## 代码证据

glibc `malloc/malloc.c` 经 `<sysdep-cancel.h>` 取得 `SINGLE_THREAD_P`，用该宏
选择是否跳过 arena 锁。上游 `sysdeps/generic/sysdep-cancel.h` 在引入 `<sysdep.h>`
后把 `SINGLE_THREAD_P` 固定为 `1`。XOS 的 `sysdeps/x86_64/xos/sysdep.h` 已采用
固定为 `0` 的上游 `sysdeps/generic/single-thread.h`，供已有 NPTL 互斥代码使用。
普通静态 C++ ELF 的 `__libc_malloc2` 直接调用 `_int_malloc` 操作主 arena，函数体
没有该 arena 的原子加锁与等待路径。该 ELF 的 `___pthread_mutex_lock` 仍有
`lock cmpxchg`、`__lll_lock_wait`，与分配器的头文件选择差异相符。

在现有静态 profile 中，多线程可在进程内交替执行，因此分配器必须保留 arena 锁。
XOS 增加 `sysdeps/xos/sysdep-cancel.h`，跟随 XOS `sysdep.h` 的加锁策略。线程准备、
线程发布、TLS 结构、析构和回收顺序继续使用现有实现。在历史 ELF 中还确认了
静态 C++ 异常状态走线程局部存储，`__libc_thread_freeres` 可达分配器线程清理。
该缺口足以破坏多线程分配器正确性，历史异常诊断中的每次失败仍需各自的证据。

## 构建与检查

在 Linux arm64 主机用 GCC 16.2.0、GNU Binutils 2.47.20260726，从锁定归档执行
`build_glibc_sdk.py --jobs 3`。glibc C SDK 清单 SHA-256 为
`cc77585fd4f30399b1a635091e3ec66c9a4f5731610d94000094bba99eee7a28`，SDK 树为
`fa26b80e6052e4ba3b49b9c4348598edcf1170057f2453c8a9862adcc1dae8ce`。
新头在源清单和 SDK 安装材料的摘要均为
`d4adb6c765559a09dd47299f6b3407a43df414d77ddd6599e48192324f4e4925`。
实际 `malloc.o.d` 引用新头，依赖文件 SHA-256 为
`22ff629d5a084923bb9a489ae0f0c55842012c2fa2c9e760b4fa9846d061c501`。

`python3 tests/glibc_static_allocator_link.py --sdk-build "$XOS_GLIBC_SDK_BUILD"`
核对归档、工具和新头的绑定，以及 `malloc.o` 的原子加锁和等待指令、pthread 互斥的
原子加锁、释放及唤醒。历史归档的分配器缺少测项中的原子加锁和等待路径。

在新 C SDK 上从签名验证成功的 GCC 16.2.0 源重建静态 libstdc++、libsupc++ 及
POSIX unwinder，核对强 pthread 引用。C++ SDK 清单与树分别为
`7eee04884a96ced6de12d20794af6809f544e3f15bc4e409b4197e58b1583d7a` 和
`b0d6dc0e59ad68ce22b4b98d03f6df26e85aa1046bc833ee1c92d04ff1652125`。
两套候选均通过 `create_xypm_profile.py` 创建和验证。将在普通客体上运行的 C 程序、
C++ 展开和 C++ 线程程序的 ELF 一并核对，确认其 `__libc_malloc2` 均含原子加锁和等待。

## 客体验证

`build.py --output-dir` 重建系统 `93efca2518543418`，镜像 SHA-256 为
`fe9c87ad7dc8ff93e1472e447f982cc69885b3f4de5111db2fb80d118793114e`，系统清单为
`71d669799356d76ed44d0c2b8315230de92047a228bf35844f7fab0577113851`。
使用 Linux arm64 上的 QEMU 11.1.3，x86_64 BIOS 客体和独立工作盘。dash 由该系统
的 SDK 构建。用 `27fd998e` 的构建器显式绑定新候选，生成下列普通静态 ELF。

| 程序 | xsh | dash |
| --- | ---: | ---: |
| `glibc_g2/static_main.c`，C 启动、堆、TLS、stdio 与退出回调 | 3/3 | 3/3 |
| `glibc_g3/threads.c`，POSIX 线程、TLS、互斥、等待与退出 | 3/3 | 3/3 |
| `cpp_abi/string_vector_probe.cpp`，C++ 标准库 | 3/3 | 3/3 |
| `cpp_abi/exception_probe.cpp`，C++ 展开、对象析构与捕获 | 3/3 | 3/3 |
| `xypm/glibc_profile_program.cpp`，`std::thread`、线程局部对象、主线程异常捕获 | 3/3 | 3/3 |

30 次运行的退出状态均符合夹具预期，资源恢复至 `[129700, 3, 1]`。报告位于
`build/runtime_lock_qualification/guest/report.json`，摘要为
`3ad65608c7f0d1b8e2d5fda373ffd7d0dd73a1d5aa28c0ed008f79426b1adcb1`，串口为
`8fe917727fe20de5fd5f57a1f25baea787873bd34242459585579ca3378c6e40`。
历史并发异常压力项目未运行。默认切换、存量迁移和整个组合树的验收仍按各自条件推进。
