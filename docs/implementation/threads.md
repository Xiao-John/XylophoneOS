# E13-T 多线程实现与验收

2026-10-25；基线 `9c896df90c2d589989b5888a495108b36959c684`，独立分支
`codex/threading-t0-t2`。实现范围取自 `../contracts/threading.md` v1 和 0036 交接。
本页与 0037 工作记录区分实现、客体证据和未运行项目；正式冻结结果见
`reports/threading_20261025/qualification.json`，原始本机产物在 `build/`。

## 范围与所有权

采用 1:1 内核线程、单核 PIT 抢占、内核不可抢占。普通进程无需 spawn 权限即可
创建自身线程；线程共享 PID、地址空间、256 MiB 用户页预算、构造/委派权限、
文件会话和管道引用。TID 是独立的非零单调标识，不因槽重用而复用。

- process_record 保留页表、父子/完成记录、权限、文件端点、stdio/pipe、堆和退出仲裁。
- thread_record 保留上下文、内核栈、FS base、FPU、等待、join/detach 和线程结果。
- core/thread_lifecycle.hpp 不包含 ISA 指令；寄存器、TLS 布局和页表操作留在 x86_64。
- files 服务继续枚举 8 个进程会话、使用内核认证的 PID；不把 TID 当作新客户端。

保持 8 个进程、每进程最多 4 个线程（含主线程、预留和未消费 join 结果）、
全局 32 槽。`ps`/旧 stats 仍按进程计数，状态由所属线程汇总。
普通 ELF 主线程仍为 128 KiB；历史可信 bootstrap 服务栈边界单独报告。
新线程默认 256 KiB，允许页对齐的 64 KiB–2 MiB，独立无映射 guard，独立 4 KiB
内核栈和 FXSAVE 区。内核文件/内存启动预算仍由原构建入口实际检查。

## ABI v1 与地址图

`src/shared/include/xos/thread_abi.hpp` 是唯一数值定义。sys0–37、startup v1/v2、
process_status（48 B）和旧 process_stats（16 B）保持兼容。

| syscall | 操作 | 布局/结果 |
|---|---|---|
| 38 | prepare | 请求 40 B；输出 reservation 56 B；仅预留，不运行 |
| 39 | start | 请求 56 B；验证入口 RX、栈范围/对齐、TP 所属区后提交 |
| 40 | abort | 限本进程预留 TID；回滚页、页表和内核栈 |
| 41 | info | 输出 56 B：本 PID/TID、实际栈界和 TP |
| 42–43 | begin_exit / exit | 最后线程仲裁、退出值和安全回收 |
| 44–45 | join / detach | 唯一 join 权；等待进入 blocked；结果消费一次 |
| 46 | monotonic / resolution | selector 0/1；启动以来纳秒/分辨率 |
| 47 | sleep_until | 绝对单调截止时间，UINT64_MAX 无限 |
| 48 | wait_word | 40 B 请求：地址、expected_u32、绝对 deadline |
| 49 | wake_word | 地址、最大数量；FIFO，返回实际唤醒数 |
| 50 | thread_stats | 48 B：进程/线程/预留/等待/结果、空闲物理页及本进程页/内核栈页 |
| 51 | process_begin_exit | 关创建入口、停止同组其他上下文，再交用户收尾 |
| 52 | profile | 16 B header；显式确认线程 arena 可用 |

结构 header 为固定宽度 version/size/reserved，保留字段和未使用参数严格校验；
输入复制为内核快照。错误保留 EFAULT、EINVAL、EPERM、EAGAIN、ENOMEM、EBUSY、
ETIMEDOUT、ESRCH、EDEADLK、ENOTSUP 的区别；pthread 返回正错误号。

| 地址范围 | 用途 |
|---|---|
| 0x40000000–0x5fe00000 | 新线程 SDK 的静态 ELF 映像 |
| 0x5fe00000–0x60000000 | 保留旧主线程静态 TLS arena |
| 0x60000000–0x70000000 | 原进程共享堆 |
| 0x70000000–0x71000000 | 4 个 4 MiB 线程 slot；slot 内低端 TLS、高端向下栈及 guard |
| process_stack_bottom/startup_begin | 原主栈/启动页，常量保持原值 |

旧 ELF 的可装载地址范围没有整体收窄；sys52 若发现它在新 arena 有映射，返回
ENOTSUP。新 linker profile 增加映像结束断言。客体专门运行一个占用 0x70000000
的旧布局 ELF，验证它仍可装载，线程 opt-in 明确拒绝。

## 创建、等待与退出

prepare 预留配额/内核栈/零页；SDK 从静态映像模板复制 .tdata、保留零 .tbss，
初始化每线程 reent/入口记录，再 start。失败路径真实回滚，不重跑全局构造、
不清 BSS、不重置堆。页表 unmap 回收空用户叶表，避免长期创建/abort 累积表页。

wait 的键是进程身份和对齐的 32 位用户地址。比较、排队与 blocked 状态转换在
同一内核临界区完成；先 wake 不留下信用，值已变优先于超时。PIT 当前报告 10 ms
分辨率，按非递减计数到期，不把 uptime 当墙钟。等待 word、process_wait 和 join
输出页均有映射生命周期保护，相关堆页解除映射返回 busy。

正常线程先清 C++ TLS，再做最多 4 轮 TSS 析构并释放/重置 reent，之后 begin_exit。
最后线程原子关创建入口并撤销未提交创建；若其他线程已 begin_exit 但仍在最终
退出路径，最后者阻塞等其安全停止，才领取进程收尾。内核不调用用户析构。
测试强制把同伴抢占在 begin_exit 与 exit 之间，检查最后者不能提前收尾。

死线程栈/TLS/内核栈在其他安全上下文尽快回收；joinable 只保留小型结果和槽。
join 输出不得位于目标即将回收的栈/TLS。自 join 为 EDEADLK，活跃 detached/
已有 join 者为 EINVAL；成功 join 或自动回收后 TID 失效，后续为 ESRCH。
线程异常、_exit、监督 kill/Escape 停止整个进程；异常日志保留实际 PID/TID/向量/地址。

## 线程 SDK 与锁序

普通 `build/sdk` 不导出线程创建库；T0 机制库独立放在 `build/threading_core`，
只用于定向探针。一般应用使用 `build/threading_sdk`，不能混用旧 single 库。

newlib 4.6 重建为动态 __getreent、真实 retargetable 锁及进程级 stdio/atexit。
FS:8 指向本线程控制块，不在抢占切换中修改共享 _impure_ptr。libstdc++/libsupc++
重建使用 pthread gthread；libgcc 从同版本已记录基底替换 5 个线程相关成员，
配置/输入/产物哈希写入 SDK manifest，原 single 归档保留。

FD 表锁只做短查找、发布和引用调整；每次 I/O pin 对象，再在表锁外取得对象锁。
同一 open 对象的 seek/read/write 偏移串行，最后 close 可延迟到在途操作放 pin。
对象 I/O → 会话锁；FD 表锁不跨 RPC/分配。目录、cwd、spawn 和堆 break 有各自锁；
spawn 先复制/pin 描述符与 cwd/env，再调用 loader。newlib stdio/allocator/env 锁
使用真实 pthread 后端。FILE 可在创建者线程退出后继续由进程其他线程使用。

所有 Client 实例共用进程会话锁，覆盖准备 request、send、recv 与检查 response；
请求 ID 在整个进程单调分配，init/超时不复用，避免迟到回复匹配到另一个 Client。
复合 seek+read、分开调用的 staging 事务及依赖 cwd/env 的复合应用操作仍需应用同步。

首版提供 create/self/equal/join/detach/exit、栈/分离属性、normal/errorcheck/
recursive mutex/trylock、cond、once、TSS 和实际栈查询。once 初始化抛异常或线程
退出会清除在途标记；TSS key 删除不调用析构。重入退出不会陷入析构死循环。

## 构建与使用

宿主固定 GCC/G++ 16.2.0、Binutils 2.47.20260726、NASM 3.02；实际 QEMU 11.1.2，
pc-i440fx-10.0/qemu64、512 MiB、单核、无网络。工具实际哈希见冻结回执。
正常 make build 不下载依赖；线程 SDK 需要显式准备源包：

- newlib-4.6.0.20260123.tar.gz：`6ff27e3bf022666f43f7802255be680eeff722ac181b1725d21e2e8318604ee3`
- gcc-16.2.0.tar.xz：`e6738e29597f733270731aa90600f37ffdc045079dfc27ec7e8192cc81085c3e`

```sh
python3 scripts/build_threading_newlib.py --archive /path/newlib-4.6.0.20260123.tar.gz
# 核对 GCC 源包 SHA256 后，解压到独立忽略目录。
mkdir -p .cache/xos_seed/threading_sources
tar -xf /path/gcc-16.2.0.tar.xz -C .cache/xos_seed/threading_sources
make threading-smoke GCC_SOURCE=.cache/xos_seed/threading_sources/gcc-16.2.0 QEMU=/path/qemu-system-x86_64
```

测试复制独立 boot image，创建/使用专用临时 FAT 工作盘；宿主只准备夹具和检查
产物，创建、调度、等待、TLS、同步、文件访问和编译器执行均发生在真实 XOS。
生成库、各份报告与最终 `build/threading_qualification.json` 互相绑定。

独立应用示例（SDK 内 helper 先核对完整产物清单）：

```sh
python3 /path/threading_sdk/compile.py --c app.c -o app.elf
python3 /path/threading_sdk/compile.py app.cpp -o app.elf
# 将 ELF 安装到自己的候选工作盘，进入 XOS 后 exec-file /path/app.elf。
```

## 本次冻结结果

最终系统 `b33da3d9929ace75`，内核文件 356,412 B；boot image SHA256：
`3d1ee35e2e69216918b30742f4c32935dc5a243a2ac8a649cdef9d845ffdcba3`。
SDK manifest SHA256：`ee633a59f24a31da1ab8f302a8189c9313aa08171ff6b63735e49658b38477ed`。

| 真实客体检查 | 结果 |
|---|---|
| T0/T1：含真实部分创建 ENOMEM 回滚、FIFO、退出屏障、跨 PID 同 VA 等 | 15 组通过 |
| pthread/newlib：含 C、errno/strtok、FILE 跨线程存活、env/目录、递归退出 | 10 组通过 |
| C++：含强制切换时活动异常、once 异常重试、TLS/guard/chrono、旧布局 | 10 组通过 |
| 原 E04/E08-2/E03/E06/E07 | 13+5+12+3+4=37 项通过 |
| 发布版 GCC/G++ 在新内核内实际编译/运行、错误、源码 sync/资源 | 6 组通过 |

合计 78 组。另有 SDK 输入/产物一致性、AArch64 通用代码实际生成对象的编译检查
以及 7 份许可证材料核对；不把宿主检查计作客体功能。公开回执/成功和失败日志
见 [冻结材料](../reports/threading_20261025/README.md)，完整本机报告在 build/。
原生编译器回归对 SHA 已核验的 0.0.1 images 包提取私有工作盘，不更改原包。

## 边界与尚未运行

- 本次是 T0–T2 定向功能/竞态与受影响回归，完整结果和失败过程在 0037/冻结回执。
- 本页T0–T2输入未运行T3专项、SMP/长时间压力或第二ISA启动；后续T3-PY
  已由独立输入验收，见[用户态摘要](../history/userland.md)，T3-QT仍未验。
- 不承诺完整 POSIX pthread、动态 TLS/加载、异步取消、robust/进程共享锁、实时
  调度/优先级继承、调用者提供栈、POSIX sem 或任意锁环检测；请求明确失败。
- 公开 C++ 子集以实际 thread/mutex/condition_variable/call_once/TLS/异常/guard/
  steady_clock 探针为准；没有声称完整 C++ 标准库线程审计或上游测试全绿。
- 无墙钟/熵。C realtime timed wait 为 ENOTSUP；getentropy 为 ENOSYS。GNU patch
  0008 让 noexcept system_clock::now 显式终止，不伪造日期或读未初始化结果。
- 普通线程 return 会正常结束该函数作用域；pthread_exit 不提供 GNU forced-unwind
  或取消语义。用户对象/锁必须正确管理生命周期，非 robust 锁不修复持锁线程退出。
- exit 停止其他线程后，若它们持有收尾所需用户锁，仍可能阻塞；请先 join 再正常
  exit，监督 kill/_exit 是强制退出入口，不冒称运行了其他线程析构。
- 旧发行、旧 SDK、CPython bootstrap 与包管理 whitelist 未静默升级；没有新 Release。
  新库仅本地验收。原 GNU 源包/补丁/构建方法及许可材料保留，逐成员许可映射和
  新二进制公开分发材料审查仍另验。
