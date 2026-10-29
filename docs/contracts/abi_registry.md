# ABI分配与协作登记

2026-10-27。登记受xos_plan.md第一部分约束；这是当前分配记录，不是功能完成表。
实现/登记不一致时先核共享定义、调用方与证据，再修登记或实现；不能用改表掩盖ABI破坏。

## syscall号段

| 起始 | 结束 | 状态 | 责任范围 |
|---:|---:|---|---|
| 0 | 0 | reserved | 既有空位，禁止擅自使用 |
| 1 | 66 | allocated | 现有分配，逐项见下表；不重新编号 |
| 67 | 79 | reserved | 内存线：VMA/映射机制；具体接口尚未设计 |
| 80 | 95 | reserved | 系统底座线：通用等待/信号/进程控制；具体接口尚未设计 |
| 96 | 111 | reserved | 显示/输入线的后续机制；现有65/66保留 |
| 112 | 65535 | unallocated | 不存在私有试用号；先通过登记PR分配，扩大范围亦须明确登记 |

责任是模块角色，不代表已派出agent或允许同时改公共文件。预留不生成头文件常量、假函数、
成功桩或能力声明，也不保证未来一个需求一定需要新syscall。112以上未分配，不暗示ABI只允许16位。

## syscall逐项登记

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

## 待实施的具体预分配

当前没有具体新接口，只有上述模块号段预留。认领时按此表登记，状态必须为claimed：

| 编号 | 拟用符号 | 责任角色 | 状态 | 实现PR |
|---:|---|---|---|---|

claimed必须位于对应reserved段，不能与现有接口或其他认领重复；不生成源码常量或能力。
实现PR再将该号从认领表移到逐项分配表，并拆分号段：该号allocated，其余仍reserved。
分配不等于验收通过，已实现但未验的能力仍按专项状态标明。

## 服务协议命名空间

| 命名空间 | 当前分配/版本 | 下一项登记责任 |
|---|---|---|
| files op | wire v2、op1–25；20clone_session、21anonymous、22seal、23/24维护、25truncate | 文件/包管理共用服务，由文件协议负责人整合；不得各自追加同一个next op |
| display action / operation | v1控制action0–9、request operation1–6 | 显示负责人；Qt通过用户态display_client接入，不另造同名内核接口 |
| startup/exec | startup1/2/3、.xos.exec/v3身份标记，线程profile另列 | loader/SDK负责人，升级须说明旧二进制准入/拒绝与迁移 |
| boot_info | v1 64字节；显示扩展v2 112字节；payload descriptor独立 | 引导/内核共同登记，不借用对方字段 |
| endpoint/PID/TID | 内核按生命周期分配的运行时身份 | 不预留静态数字给Qt，不以程序名或客户端自填身份授予权利 |
| SDK manifest | process_extensions与display_extensions等能力/输入标识 | 普通/线程生成器同步；reserved不登记为supported |

每个op只在其服务/协议版本内解释，不与syscall共用“全球号表”。上述服务具体布局仍以
共享头和专项契约为准；若新需求改变结构，必须独立评估版本/尺寸/向后兼容，不只抢新编号。

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
