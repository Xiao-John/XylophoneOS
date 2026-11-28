# libc与运行库适配

现行默认开发入口见 [glibc host SDK](releases/glibc_host_sdk.md)。本页的 newlib
条目保留 2026-10-27 起的实现基线；具体产物、配置和摘要仍以对应 SDK manifest
为准，不把旧 `build/sdk` 或某一 libc 的资格转移到另一套运行库。

## 当前实现

- CRT正常初始化/退出、heap、stdio、errno、文件/目录与受限posix_spawn；C++运行库、
  构造/析构、异常/RTTI、静态TLS和线程接入有各自gate，见[E08](e08.md)、[线程实现](implementation/threads.md)。
- SSE/x87按任务/线程保存，newlib/应用可使用所需ABI；内核仍遵循受限C++与寄存器约束。
- 普通SDK与线程SDK分开，后者使用newlib重入状态、锁/TSS/TLS和线程安全适配；不能用
  freestanding默认single线程模型替代真实pthread，也不覆盖旧冻结SDK。
- 文件描述符映射到files对象引用；共享打开描述、dup/CLOEXEC、32FD exec转交与匿名文件
  见[SDK](e04_loader_sdk.md)、[Shell](implementation/shell.md)。当前FD不代表完整POSIX。
- getentropy→sys63真实RDRAND接口；墙钟/gettimeofday→sys64，单调时间/睡眠走线程等待
  机制。输出大小、errno、不支持/硬件失败按各自契约；不以uptime或固定种子补安全接口。
- 线程 SDK 可由公开归档重建：`newlib-4.6.0.20260123.tar.gz` 取自 sourceware
  （sha256 `6ff27e3bf022666f43f7802255be680eeff722ac181b1725d21e2e8318604ee3`），
  再跑 `build_threading_newlib.py` 与 `build_threading_sdk.py`。本机已用该 SDK 实测
  lz4 `-T2`、zstd `-T2` 的压缩/解压在客体通过。
- 线程运行时补齐常用 P2 面：`sem_init/wait/trywait/timedwait/post/getvalue`（基于 mutex/cond）、
  `pthread_barrier_*`、`pthread_spin_*`、`pthread_setname_np/getname_np`、attr guardsize、
  `pthread_condattr_getpshared`、`pthread_rwlockattr_*`；普通 SDK 提供同名单线程实现。
  `pthread_tryjoin_np/timedjoin_np/getcpuclockid` 目前诚实返回 `ENOTSUP`。
- 线程包使用 profile `xos-x86_64-static-threaded-v1`（features 含 `threads`，登记线程
  SDK 树哈希与已验证系统 build）；xypm 事务按该 profile 建库。
- 普通 SDK 提供**单线程 pthread 子集**：`pthread_once`、TSS keys、mutex/cond/rwlock、
  `pthread_self/equal`、`sched_yield` 在单线程进程里语义正确；`pthread_create/join/detach`
  返回 `ENOSYS`。声明需要 POSIX feature 宏（`xos_app.py` 已带），真实多线程仍需线程 SDK。
- 控制台 `read()` 是阻塞语义：内核只提供非阻塞轮询，libc 在 `EAGAIN` 时以 1 ms
  `sys_sleep_until` 重试，并把 Enter 的 CR 映射为 NL（旧控制台没有行规程）。
  `O_NONBLOCK` 仍返回 `EAGAIN`。
- `times()`/`clock()` 用单调时基（1000 tick/秒，非线程 CPU 计时）；C11 `timespec_get`
  走 sys64 纳秒。`utime`/`chmod`/`chown` 已提供可链接符号但返回 `ENOSYS`——文件服务
  尚无时间戳/权限/所有权写 ABI，不伪造成功。`clock_gettime`/POSIX timers 的头文件
  可见性受 `_POSIX_TIMERS` 控制，本组未开启，见[端口反馈账本](ports_ledger.md)。
- truncate/ftruncate接files op25；stat仍有合成属性。权限、链接、完整时间元数据、locale、
  signals、socket、通用就绪等待与mmap族未取得完整资格，缺项不能永远成功。

## 构建与使用

普通构建scripts/user_build.py导出头/CRT/libxos/libxos_loader/newlib/user.ld及许可，
scripts/build_threading_sdk.py另建线程/可选C++ SDK。第三方应用使用冻结SDK/profile，
见[快速开始](friend_user_program_quickstart.md)；不默认修改系统程序清单来安装软件。

适配集中于src/user/libc/newlib_syscalls.cpp、src/user/threading/与对应SDK/架构CRT。
新增接口同步公共定义、普通/线程生成器和真实消费者；pthread直接错误号与errno型接口
分别处理，不把同一个负内核返回无差别传播。

## 验收与许可

初版printf/malloc/string/exit和FXSAVE检查见[E01–E07](history/e01_e07.md)；原生C/C++、
线程、CPython与SDK身份绑定各自保留冻结证据。当前程序可运行不等于newlib全部接口合规。
newlib包含多来源许可；声明/组件清单见[许可管理](licensing.md)。材料检查与预构建库逐成员
归属审计分开：成员→源文件→声明类别的映射见
[newlib 成员许可映射](reports/newlib_member_license_20261103/)（1053/1053 全覆盖），
它不是逐成员法律意见，也不以libc文件名推定单一LGPL授权。

## glibc 时钟 API（Issue #124）

当前源码的 `clock_getcpuclockid(0, ...)` 与显式自身 PID 返回进程 CPU 时钟，
复用既有 sys89 v1 的计数及实际分辨率；返回值随后可用于 `clock_gettime` 和
`clock_getres`。其它进程返回 `ENOSYS`，计数不可用时传播实际错误；此函数返回
正错误号，失败不修改输出，也不改变调用者的 `errno`。

glibc 的 `clock_nanosleep` 适配使用既有 sys47 单调绝对等待。`CLOCK_MONOTONIC`
和 `CLOCK_REALTIME` 的相对等待均按单调经过时间计算；绝对 realtime 等待在唤醒后
重新核对墙钟，防止两次采样间的抢占造成提前返回。时间换算和期限相加均检查溢出。
上游 `nanosleep` 包装层直接复用此适配，并将正错误号转换为 `-1/errno`。

仅支持经过时间等待；CPU 时间睡眠返回 `ENOTSUP`。没有新增墙钟设置、信号中断
或异步线程取消语义，成功或失败均不伪造剩余时间。POSIX 定时器及目标线程 CPU
时钟由各自的 Issue #124/#125 变更和资格说明覆盖。

源码、SDK、双 Shell 客体及边界检查记录见
[df317843](work_log/df317843_issue124_glibc_clock_apis.md)。
