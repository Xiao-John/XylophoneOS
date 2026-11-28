# ABI分配与协作登记

2026-10-27。登记受xos_plan.md第一部分约束；这是当前分配记录，不是功能完成表。
实现/登记不一致时先核共享定义、调用方与证据，再修登记或实现；不能用改表掩盖ABI破坏。

## syscall号段

| 起始 | 结束 | 状态 | 责任范围 |
|---:|---:|---|---|
| 0 | 0 | reserved | 既有空位，禁止擅自使用 |
| 1 | 66 | allocated | 现有分配，逐项见下表；不重新编号 |
| 67 | 67 | allocated | 匿名虚拟内存 v1。VM3 恢复后的限定客体证据见[记录](../work_log/58b24599_vm3_lifecycle_sdk.md)，完整资格待验 |
| 68 | 79 | reserved | 内存线：VMA/映射机制 |
| 80 | 80 | allocated | 通用字节流授权；实现未验 |
| 81 | 81 | allocated | 通用受控 IPC；实现未验 |
| 82 | 82 | allocated | 受控设备 PIO；COM1 与 PC Speaker 资源见契约，未客体验收 |
| 83 | 83 | allocated | 受控 IRQ 事件；实现未验 |
| 84 | 86 | allocated | Interactium IPC channel readiness and service-name registration/connection |
| 87 | 87 | allocated | SL1 创建能力；P1-B 显式 modes 4/5 为版本 1 进程树累计预算和归因查询，见 [契约](process_tree_budget.md)。旧 modes 0–3 保持。 |
| 88 | 88 | allocated | 通用 IPC v1；IP2/IP3 有既有客体记录，IP4 bulk 可调用但本组合 guest 未运行，IP5 性能资格独立 |
| 89 | 89 | allocated | 自身进程/当前线程 CPU 时间；版本 1，已实现但未客体验收 |
| 90 | 90 | allocated | `sys_observe` v1：自身/直接子进程、持有 IPC 端点的有界只读观测；[契约](native_observation.md)，资格见专项记录 |
| 91 | 95 | reserved | 系统底座线：通用等待/信号/进程控制；其余接口尚未登记 |
| 96 | 111 | reserved | 显示/输入线的后续机制；现有65/66保留 |
| 112 | 112 | allocated | 设备授权线 v1 `sys_device`。grant/MMIO/DMA/IRQ/撤销已实现，已有[网络纵切限定客体证据](net_user_driver.md)，通用资格见[契约](device_authorization_v1.md)§9 |
| 113 | 127 | reserved | 设备授权线：后续机制 |
| 128 | 65535 | unallocated | 不存在私有试用号；先通过登记PR分配，扩大范围亦须明确登记 |

责任是模块角色，不代表已派出agent或允许同时改公共文件。预留不生成头文件常量、假函数、
成功桩或能力声明，也不保证未来一个需求一定需要新syscall。128以上未分配，不暗示ABI只允许16位。

## syscall逐项登记

sys87 modes 4/5 分别接收 `process_budget_config`（64 bytes）与
`process_budget_snapshot`（192 bytes），共享定义 `process_budget_abi.hpp`。
预算沿 fork/spawn/exec 保留所有祖先域；暂存页与仍有别名的资源也计费。
版本、权限、错误、生命周期和六维范围见 [P1-B 契约](process_tree_budget.md)。

sys51 显式 mode 1 为有界进程清理窗口，32 字节版本 1 请求，旧 mode 0 保持。
独占退出责任、30 秒单调 deadline 上限及失败/回滚语义见
[线程契约](threading.md#有界进程清理窗口sys51-mode-1)。

sys84–86 端点、待 accept 连接及发布名称在成功 exec 时按
[endpoint 生命周期](ipc_endpoint_lifecycle.md) 一起撤销，失败 exec 完整保留；
sys81 的显式 channel 继承仍由原契约约束。
sys84 create 与 sys86 connect 共用每 PID 4 个 pair 的额度（含 pending 与已 accept
连接），sys86 publish 每 PID 最多 2 个名称；超额返回既有 resources，失败不修改
输出或已建立对象。共享常量与两个 SDK manifest 同步，详见同一生命周期契约。

sys60 试行 bit32 扩展 entry 可显式保留通用通道，布局见 `process_exec_channel_entry`
和 [通道契约](channel.md)；默认 ABI 不变，尚未客体验证。
sys81 试行 action 4 对最多四个通用端点做原子检查与等待，布局见
`channel_wait_many_request` 和同一契约；尚未客体验证。
sys81 action 5 试行派生 fork 子进程双向通道，结构为 `channel_fork_pair`；
身份、额度和生命周期见同一契约，尚未客体验证。
action 6 由对端验证派生通道来源，结构为 `channel_fork_verification`；
见同一契约，尚未客体验证。

sys35 第三参数登记为 `process_tls_mode`：0 `building_child` 保留父进程设置
owned building 子进程主线程指针；1 `current_thread` 允许调用线程安装自身运行库
分配的线程指针，第一参数必须为当前 PID。其它模式拒绝。权限、地址与生命周期
校验见 [线程契约](threading.md#当前线程安装运行库线程指针)。本扩展供隔离 glibc
G2/G3 候选使用，SDK 单独记录能力与客体验证；不更换默认 libc。

sys41 第二参数 mode 1 为同进程目标线程 CPU 查询，使用独立的 56 字节
`thread_cpu_time` v1，mode 0 原 `thread_info` 保持。sys44 第三参数可显式
指向 32 字节 `thread_join_options` v1：mode 1 立即 try，mode 2 绝对单调
期限；第三参数零保留阻塞 join。未占用新编号、未复用保留位，sys89 v1/72
字节不变。权限、旧内核拒绝、输出 pin/超时回收、负 clock ID 身份与错误见
[线程契约](threading.md#有界-join-与目标线程-cpu-时钟issue-125)。

sys20 第三参数 bit0 为非阻塞，bit1 与第一参数为零共同选择显式
[wait-any](process_wait.md)；旧精确 PID 请求的 flags 0/1 保持原行为。

数值来源分别为内核基础syscall头与共享ABI头；此表锁定当前分配，自动检查捕获重号、漏项、
新增占用预留段而未登记，以及源码与本表偏移。allocated不等于完整POSIX或应用资格。

| 编号 | 符号 | 定义来源 |
|---:|---|---|
| 1 | `sys_write` | `src/kernel/include/xos/syscall.hpp` |
| 2 | `sys_exit` | `src/kernel/include/xos/syscall.hpp` |
| 3 | `sys_yield` | `src/kernel/include/xos/syscall.hpp` |
| 4 | `sys_send` | `src/kernel/include/xos/syscall.hpp` |
| 5 | `sys_recv` | `src/kernel/include/xos/syscall.hpp` |
| 6 | `sys_getpid` | `src/kernel/include/xos/syscall.hpp` |
| 7 | `sys_ticks` | `src/kernel/include/xos/syscall.hpp` |
| 8 | `sys_read` | `src/kernel/include/xos/syscall.hpp` |
| 9 | `sys_tasklist` | `src/kernel/include/xos/syscall.hpp` |
| 10 | `sys_kill` | `src/kernel/include/xos/syscall.hpp` |
| 11 | `sys_handle_write` | `src/shared/include/xos/process_abi.hpp` |
| 12 | `sys_handle_read` | `src/shared/include/xos/process_abi.hpp` |
| 13 | `sys_handle_close` | `src/shared/include/xos/process_abi.hpp` |
| 14 | `sys_image_info` | `src/shared/include/xos/process_abi.hpp` |
| 15 | `sys_image_read` | `src/shared/include/xos/process_abi.hpp` |
| 16 | `sys_process_create` | `src/shared/include/xos/process_abi.hpp` |
| 17 | `sys_process_map` | `src/shared/include/xos/process_abi.hpp` |
| 18 | `sys_process_start` | `src/shared/include/xos/process_abi.hpp` |
| 19 | `sys_process_abort` | `src/shared/include/xos/process_abi.hpp` |
| 20 | `sys_process_wait` | `src/shared/include/xos/process_abi.hpp` |
| 21 | `sys_process_stats` | `src/shared/include/xos/process_abi.hpp` |
| 22 | `sys_ipc_handles` | `src/shared/include/xos/process_abi.hpp` |
| 23 | `sys_block_read` | `src/shared/include/xos/process_abi.hpp` |
| 24 | `sys_block_write` | `src/shared/include/xos/process_abi.hpp` |
| 25 | `sys_block_sync` | `src/shared/include/xos/process_abi.hpp` |
| 26 | `sys_block_info` | `src/shared/include/xos/process_abi.hpp` |
| 27 | `sys_file_session` | `src/shared/include/xos/process_abi.hpp` |
| 28 | `sys_process_grant` | `src/shared/include/xos/process_abi.hpp` |
| 29 | `sys_heap_break` | `src/shared/include/xos/process_abi.hpp` |
| 30 | `sys_pipe_create` | `src/shared/include/xos/process_abi.hpp` |
| 31 | `sys_pipe_read` | `src/shared/include/xos/process_abi.hpp` |
| 32 | `sys_pipe_write` | `src/shared/include/xos/process_abi.hpp` |
| 33 | `sys_pipe_close` | `src/shared/include/xos/process_abi.hpp` |
| 34 | `sys_process_stdio` | `src/shared/include/xos/process_abi.hpp` |
| 35 | `sys_process_tls` | `src/shared/include/xos/process_abi.hpp` |
| 36 | `sys_debug_trace` | `src/shared/include/xos/process_abi.hpp` |
| 37 | `sys_process_delegate` | `src/shared/include/xos/process_abi.hpp` |
| 38 | `sys_thread_prepare` | `src/shared/include/xos/thread_abi.hpp` |
| 39 | `sys_thread_start` | `src/shared/include/xos/thread_abi.hpp` |
| 40 | `sys_thread_abort` | `src/shared/include/xos/thread_abi.hpp` |
| 41 | `sys_thread_info` | `src/shared/include/xos/thread_abi.hpp` |
| 42 | `sys_thread_begin_exit` | `src/shared/include/xos/thread_abi.hpp` |
| 43 | `sys_thread_exit` | `src/shared/include/xos/thread_abi.hpp` |
| 44 | `sys_thread_join` | `src/shared/include/xos/thread_abi.hpp` |
| 45 | `sys_thread_detach` | `src/shared/include/xos/thread_abi.hpp` |
| 46 | `sys_clock_monotonic` | `src/shared/include/xos/thread_abi.hpp` |
| 47 | `sys_sleep_until` | `src/shared/include/xos/thread_abi.hpp` |
| 48 | `sys_wait_word` | `src/shared/include/xos/thread_abi.hpp` |
| 49 | `sys_wake_word` | `src/shared/include/xos/thread_abi.hpp` |
| 50 | `sys_thread_stats` | `src/shared/include/xos/thread_abi.hpp` |
| 51 | `sys_process_begin_exit` | `src/shared/include/xos/thread_abi.hpp` |
| 52 | `sys_thread_profile` | `src/shared/include/xos/thread_abi.hpp` |
| 53 | `sys_boot_payload` | `src/shared/include/xos/process_abi.hpp` |
| 54 | `sys_pipe_wait` | `src/shared/include/xos/process_abi.hpp` |
| 55 | `sys_process_foreground` | `src/shared/include/xos/process_abi.hpp` |
| 56 | `sys_process_cancel` | `src/shared/include/xos/process_abi.hpp` |
| 57 | `sys_process_fork_prepare` | `src/shared/include/xos/process_abi.hpp` |
| 58 | `sys_process_fork_commit` | `src/shared/include/xos/process_abi.hpp` |
| 59 | `sys_process_fork_files` | `src/shared/include/xos/process_abi.hpp` |
| 60 | `sys_process_exec_commit` | `src/shared/include/xos/process_abi.hpp` |
| 61 | `sys_process_exec_prepare` | `src/shared/include/xos/process_abi.hpp` |
| 62 | `sys_process_guard` | `src/shared/include/xos/process_abi.hpp` |
| 63 | `sys_random_bytes` | `src/shared/include/xos/process_abi.hpp` |
| 64 | `sys_clock_realtime` | `src/shared/include/xos/process_abi.hpp` |
| 65 | `sys_display` | `src/shared/include/xos/display_abi.hpp` |
| 66 | `sys_display_present` | `src/shared/include/xos/display_abi.hpp` |
| 67 | `sys_vm` | `src/shared/include/xos/vm_abi.hpp` |
| 80 | `sys_stream_lease` | `src/shared/include/xos/process_abi.hpp` |
| 81 | `sys_channel` | `src/shared/include/xos/process_abi.hpp` |
| 82 | `sys_pio_grant` | `src/shared/include/xos/process_abi.hpp` |
| 83 | `sys_irq_event` | `src/shared/include/xos/process_abi.hpp` |
| 87 | `sys_process_authority` | `src/shared/include/xos/process_abi.hpp` |
| 88 | `sys_ipc_v1` | `src/shared/include/xos/ipc_v1_abi.hpp` |
| 89 | `sys_process_cpu_time` | `src/shared/include/xos/process_abi.hpp` |
| 90 | `sys_observe` | `src/shared/include/xos/observation_abi.hpp` |
| 112 | `sys_device` | `src/shared/include/xos/device_abi.hpp` |
| 84 | `sys_ipc_endpoint` | `src/shared/include/xos/process_abi.hpp` |
| 85 | `sys_ipc_wait` | `src/shared/include/xos/process_abi.hpp` |
| 86 | `sys_ipc_name` | `src/shared/include/xos/process_abi.hpp` |

sys85 mode 4 为调用者当前 Files 回复端点的绝对期限等待。
[端点生命周期契约](ipc_endpoint_lifecycle.md#文件回复等待)
的 Files mode 4 保持；generic 端点新增 sys85 mode 5 `receive_until` 与 mode 6
`send_until`，第三参数是绝对单调纳秒期限。就绪优先，未就绪且到期返回现有
thread timeout；零期限立即检查，最大 u64 无限。布局及旧 mode 0–4 不变。

## 待实施的具体预分配

sys54 的管道显式截止时间扩展已由 dash_c1 `pipe_probe` raw 模式客体验收（过期截止返回 thread_error_timeout(-13)，2026-11-10 C1 23/23 全绿）；console 等待因 C28 撤回，详见
`e04_loader_sdk.md`；原第三参数为零时的行为保持。

PX4-A 提议认领如下；本分支未合入前不构成全项目登记，不生成源码常量或能力：

| 编号 | 拟用符号 | 责任角色 | 状态 | 实现PR |
|---:|---|---|---|---|
| 67 | `sys_vm` | VM负责人；匿名私有VMA v1 | allocated | 已实现，完整资格待验。[契约](anonymous_vm.md)与[恢复记录](../work_log/58b24599_vm3_lifecycle_sdk.md) |
| files op 29 | `file::op::set_metadata` | 文件/包管理共用服务；FAT 诚实子集 | allocated (M1) | [契约](file_metadata_v1.md)；`tests/file_metadata_guest.py` |
| files op 30/31 | `file::op::read_at/write_at` | G3 文件模块；显式位置，不改共享 offset | allocated | [契约](glibc_files_v1.md#定位读写与目录流)；`tests/glibc_files_extra_host.py` |
| files op 32 | `file::op::remove_directory` | 在同一请求内确认目标为目录、为空并移除 | allocated | [路径变更](glibc_files_v1.md#路径变更)；`tests/fixtures/glibc_g3/path_mutations.c` |


claimed必须位于对应reserved段，不能与现有接口或其他认领重复；不生成源码常量或能力。
实现PR再将该号从认领表移到逐项分配表，并拆分号段：该号allocated，其余仍reserved。
分配不等于验收通过，已实现但未验的能力仍按专项状态标明。

## 服务协议命名空间

| 命名空间 | 当前分配/版本 | 下一项登记责任 |
|---|---|---|
| files op | wire v2、op1–32；20clone_session、21anonymous、22seal、23/24维护、25truncate、26cwd_set、27cwd_get、28resolve_path；29 set_metadata；30 read_at、31 write_at、32 remove_directory；op2 请求 bit12 为 list_identity；op3 请求 bit13 为 stat_check_exec，成功响应 bit3 为 stat_exec_checked | 文件/包管理共用服务；26由已认证parent_pid约束构造子继承；[文件身份与查询](file_identity.md)、[op29](file_metadata_v1.md)、[op30–32](glibc_files_v1.md)；下一操作从33协调登记 |
| display action / operation | v1控制action0–9、request operation1–6 | 显示负责人；Qt通过用户态display_client接入，不另造同名内核接口 |
| startup/exec | startup1/2/3、.xos.exec/v3身份标记；试行 startup2 flag bit16 与 reserved 承载 terminal send handle，仅限只读 `.xos.tty` v1 opt-in | loader/SDK负责人，升级须说明旧二进制准入/拒绝与迁移；glibc 终端接收 v2/v3 的受限客体资格见 [e6b8c410](../work_log/e6b8c410_glibc_terminal.md)，出站继承单独推进 |
| glibc terminal | 既有 startup kind5 正式命名为 terminal；CRT capability bit1；libc 本地 TCGETS/TCSETS/TCSETSW/TCSETSF=0x5401–0x5404，FIONCLEX/FIOCLEX=0x5450/0x5451 | [glibc_terminal_v1](glibc_terminal_v1.md)；复用 native terminal v2，glibc termios 逐字段转换，实际资格按独立工作日志 |
| boot_info | v1 64字节；显示扩展v2 112字节；payload descriptor独立 | 引导/内核共同登记，不借用对方字段 |
| dynamic identity / generation | ELF note `XOS\0`/`0x584f5301`，identity v1 128字节；generation v1 header128/object512，最多12对象 | [准入组件](dynamic_admission_v1.md)；独立文件格式，不新增 syscall 或修改 startup；公开动态启动、持久激活与 ready 仍待闭环 |
| endpoint/PID/TID | 内核按生命周期分配的运行时身份 | 不预留静态数字给Qt，不以程序名或客户端自填身份授予权利 |
| SDK manifest | process_extensions与display_extensions等能力/输入标识 | 普通/线程生成器同步；reserved不登记为supported |
| net 服务协议 | v1 information/transmit/receive/stop，raw Ethernet 1514 字节 | 用户态 VirtIO-net。[纵切契约](net_user_driver.md)记录 ARP、IRQ 与 reset 的限定客体验收 |
| net2 服务协议 | v2 64字节header，1024字节payload，operations1–9，原生TCP/UDP连接与认证多会话 | 网络用户态线。[v2 契约](net_service_v2.md)与[多应用复验](../work_log/69b0e274_network_guest_readiness_and_window.md)登记已验范围。v1 诊断显式隔离，沿用既有 syscall |
| net2 N4 预览扩展 | v2 可选 operations10–14，配置快照 48 字节、写配置 16 字节、直接 A 结果 24 字节，错误 -211 至 -217 | 仅显式构建并经受信 controller 启用。客户端先询问 configuration，旧镜像可返回 unsupported。保留 operations1–9。[N4 线格式](network_n4_v1_proposal.md#21-n4-静态解析预览线格式) |
| net2 TCP 扩展 | v2 可选 operations15–17：capabilities 16 字节、readiness 32 字节、shutdown_write 空负载 | [TCP readiness 和半关闭](net_service_v2.md#tcp-readiness-和写半关闭扩展)。先查询 capability，旧服务 unsupported 保留原阻塞传输；不改变地址授权，不包含事件订阅 |

2026-11-12 用户授权将本轮实现交付与 guest 资格分开：sys88 actions 19–23 沿用 PR #112 公开 grant
create/delegate/map/unmap/close（delegate 保持同值句柄），supported mask `0x1f` 表示可调用机制；SDK manifest
另列 bulk `guest_qualification=not_run`。sys112 沿用操作 1–11，不另占号，有限资源与
配置快照按其契约 §9 登记。旧客体和 IP5 性能记录不重绑，不以 feature 位表示已通过验证。

每个op只在其服务/协议版本内解释，不与syscall共用“全球号表”。上述服务具体布局仍以
共享头和专项契约为准；若新需求改变结构，必须独立评估版本/尺寸/向后兼容，不只抢新编号。

## P1-H / P1-K1 协作认领（2026-11-28）

本节只协调下一实现的公共接口；`claimed` 不生成源码常量、能力位或资格。
实现 PR 须同时交付共享头、调用方/服务、SDK 清单、契约与真实客体证据，
再将实际接口移入上方服务命名空间。现有 syscall 编号、布局和保留号段不变。

| 接口 | 认领者与文件范围 | 版本、用途和兼容 |
| --- | --- | --- |
| Net2 operations 19 `readiness_bind` / 20 `shutdown_read`；capability 掩码 `0x4` / `0x8` | P1-H 网络线；`net_service_abi.hpp`、Net2 service/client、glibc socket bridge | claimed；capabilities 请求 flags=1 显式选择 revision 2，flags=0 保持旧 revision 1 与原能力位。旧服务拒绝 flags=1 时回退旧查询和有限等待。复用 sys88 grant，不新增 syscall。op19 的 32 字节响应绑定 4096 字节只读客户端页、session generation；页的有效结构为版本 1、128 字节，含序列、采样单调时间和两个绑定 handle 的 readiness/result。op20 是同 socket 所有权的无负载读方向关闭；readiness 的 `0x40` 只在新版页出现，旧 op16 mask 保持。 |
| sys54 `sys_pipe_wait` 的显式 query mode `1ull << 63` | P1-H/P1-K5 共用机制；kernel pipe dispatch、`process_abi.hpp`、SDK、glibc poll | claimed；arg1 为调用者已持有的 pipe token 或 pipe stdio route，arg2 为模式值，arg3 指 32 字节版本 1 `pipe_status_snapshot`。旧 arg2=0–4096 的等待/期限含义不变，旧内核拒绝新模式。只读当前方向 byte count、方向和 peer_closed，不消费数据、不创造授权；console 拒绝。 |
| glibc `xos/sleep.h` 的 `xos_sleep_query` / `xos_sleep_interrupt` | P1-K1 运行时线；glibc XOS sleep adapter、公共头和 SDK manifest | claimed；版本 1、48 字节精确 sleep ticket，绑定 PID/TID/sequence/deadline。复用 sys48/49，既有正常 nanosleep/clock_nanosleep 保持；新机制是同进程显式中断，不是 POSIX 信号或 pthread_cancel。 |

Net2 页只对认证会话授予 read 权；服务保留写映射，连接、grant 和映射生命周期
须覆盖关闭、撤销、服务死亡和资源耗尽。seqlock 一致不等于状态新鲜：`poll(0)`
可以使用有效正就绪提示，但不能把调用开始以前的负快照当成本次 not-ready；
没有本次新鲜负快照时返回明确的 unknown/EAGAIN。有限等待沿用调用者原始绝对
期限；超时和迟到回复不能增加预算。回滚到旧服务不得把缺失能力伪造成成功。

pipe snapshot 固定为六个 u32（version、size、readable、writable、flags、reserved）
和一个 u64 reserved2，共 32 字节。flags 分别为 read_end=1、write_end=2、peer_closed=4；
未持有方向的 byte count 必须为零。先核调用者所有权，再验证可写输出和 header，
最后在同一个内核临界区采样并返回；无管道句柄、无效版本/保留位、不可写输出均真实失败。
读端 EOF 是 readable=0 且 peer_closed，写端 peer_closed 对应 EPIPE；关闭/exec 立即可见。

sleep ticket 的字段固定为四个 u32（version、size、reserved、reserved2）和
四个 u64（pid、tid、sequence、deadline_ns），合计 48 字节；所有 reserved 必须为零。
只允许查询和中断本进程当前已登记的 wait，陈旧 ticket 返回 ESRCH，重复中断返回
EALREADY，跨 PID 返回 EPERM，仍登记但已到期限返回 ETIMEDOUT。sequence 不回绕，fork 不继承活动 ticket；失败不影响
后续 wait。相对等待被中断时报告剩余单调时长，绝对等待不改 rem；clock_nanosleep
直接返回错误码且保持 errno。缺少新 API 的旧 SDK 保留原非中断语义，不能冒称支持。
四个活动槽满时返回 EAGAIN，序号耗尽返回 EOVERFLOW；线程退出清理必须验收。pthread_cancel 保持现行 ENOTSUP。

## P1-K2 / P1-K5 后续协作认领（2026-11-28）

本节 `claimed` 只协调实现，不声明能力或目标资格；没有新增 syscall 编号。

| 接口 | 角色与文件范围 | 语义和兼容 |
| --- | --- | --- |
| sys34 `sys_process_stdio` arg2=`1ull << 63` 独立 pipe 批量 transfer | P1-K5；kernel pipe/process、`process_abi.hpp`、native loader/SDK 和匹配 glibc spawn | claimed；arg1 只能是调用者拥有的 building child，排除 fork/replacement pending；arg3 指版本 1、144 字节请求，四个 u32 header（version,size,count,reserved）后接 16 项 {u32 source,target}。输入 target 与未用项皆零，source 为 caller 持有且去重的 private pipe token；整批验证和输出准备成功后一次增加 child 引用并返回 target。旧 stdio mode0–2 不变，旧内核拒绝新模式。 |
| `xos_fork_control_offer` wire v1（128 字节） | P1-K2 fork/controller 线；native loader control、glibc process adapter | claimed；复用现有受保护 launch channel 容量，独立 magic/type，不改既有 READY/ACK message 布局。header u64 magic、u32 version,size；五个 u64 controller_pid,child_pid,generation,nonce,deadline；两个 u32 ready_handle,ack_handle；40 字节 launch artifact；三个 u64 reserved。fork child 必须核内核认证对端、同 artifact/代次和绝对期限后才接受新 controller 并发 READY。 |

pipe transfer 不复制对象或扩充 authority；token 仍由 PID membership 限权，同一对象
的别名保留。16 个 native pipe references（含 stdio）与 8 个全局 pipe objects 上限保持，
不承诺 32 个独立对象。预检、COW 输出准备和批量 retain/copyout 之间不得出现部分成功；
失败不改输出或引用数。原对象的 owner/budget_mask 不变，新增引用不凭空返还树预算，
最后引用关闭才按原规则归还对象 credit。loader 后续失败通过 abort 回收整批。
SDK transfer option 默认关闭，原 caller 的 unrouted pipe 拒绝行为保持；匹配并验证的
GNU FD snapshot 路径才显式开启。startup v3 与 same-PID exec handle 保持路径不变。

fork migration 由 parent 为其真实 fork child 创建新的有界 controller 通道；child
不得继承或冒用 parent 的上游 controller 端点。parent 释放 Files 锁后才等待新 READY；
任何验证、期限或 READY 失败均 kill/wait 清理，不能把半建立 child 当作成功返回。
终端 actor dynamic exec 为独立协议和独立 PR，不用 console/Files 资格代替。
实现前后都保留原非 shared fork 和失败 exec 的权限/句柄契约。

## 分配流程

1. 使用者先提供最小缺口/探针，说明是否能复用现有SDK/IPC；Qt具体边界见qt_platform.md。
2. 在独立PR登记symbol/op、编号、角色、用途、状态、协议版本、文件占用与关联实现PR。
   先合入claimed登记，再并行实施；未合入分支的本地登记不视为全项目已同步。
3. 同一号段内仍逐号登记，不把整段交给多个agent自由取next。临时放弃保留记录或明确撤销；
   已发布/已验身份不直接回收，变更按兼容契约记录，不静默复用。
4. 实现PR同步共享头、dispatch、SDK/服务/client、两类manifest、错误/生命周期与定向探针。
   分配状态allocated与验收状态分开，未通过不写supported。执行tests/docs_consistency.py
   和tests/abi_doc_consistency.py；前者也核保留段无占用。Git无文本冲突不代表ABI无语义冲突。
5. 公共分发/头/SDK生成器由登记负责人整合；其他移植PR只在所声明文件范围工作。

当前登记已随 PR #5 合入 main；PR #8 复用现有 ABI，没有新增分配。原始编号/迁移证据见history/delivery_audit.md与
history/boot_display.md。没有预先给Qt保留专属syscall或通用内核对象类型。
