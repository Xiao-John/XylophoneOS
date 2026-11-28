# P0 通用 IPC 绝对期限等待

2026-11-27；以 `96d75c9` 的确定性生命周期模块为基础，本模块不依赖另一条
per-PID quota 分支。网络 poll 需要在服务仍存活但不回复时按调用者期限返回；
既有 sys85 generic wait 无限阻塞，而 mode 4 的期限只允许 Files 专用端点。
将网络端点混入 Files mode 会破坏认证范围，改成 sys81 则需要重建整套会话。

## 通用机制与 ABI

sys85 新增 `receive_until=5` / `send_until=6`，第三参数为绝对单调纳秒期限。
继续核对 endpoint 的内核主体和方向，复用原子 ready 检查、既有 thread wait
记录、定时器及 close/exit 撤销路径；不引入网络或服务业务进内核。
SDK 增加 `ipc_wait_until(endpoint, receive|send, deadline)`，共享头、ABI 登记、
生命周期契约和两个 SDK manifest 同步；没有新增 syscall 编号或请求结构。

就绪优先于过期期限，0 只立即检查；未就绪且到期返回现有 timeout (-13)。
blocked close 返回 broken (-7)，旧 token 后续调用仍 denied (-1)。
`UINT64_MAX` 无限，`UINT64_MAX-1` 为有效有限期限；内核只比较绝对值，不做
相对时间加法。相对期限的溢出检查或饱和是调用方责任。
旧 mode 0–3 参数与行为不变；Files mode 4 仍独占专用端点，保留先判断期限的
既有次序。SDK manifest 的通用生成资格仍 not_run，实测资格绑定本报告的输入。

timeout 不发送、消费或撤回消息，也不证明业务尚未执行。调用者要保存请求编号
与迟到回复状态，或按协议废弃会话；有副作用请求不能自动重放。新 mode 只有在
旧内核返回 invalid (-2) 时才可能走明确有界的兼容策略，denied/broken/timeout
不能当作能力缺失。网络模块负责 poll 的迟到回复与请求状态管理。

## 实现验收

原 native IPC fixture 的公共收发、身份验证和 blocked 观测移入
`tests/fixtures/ipc_common.hpp`；新 deadline fixture 与原生命周期套件复用它。
构建器共享同一个显式 native worker profile，runner 增加 `--suite deadline`。
不会把单线程 libc 当作多线程运行库。

使用 XOS SDK Preview 2 常规 Bubblewrap launcher，GCC 16.2.0、Binutils
2.47.20260726、NASM 3.02；当前源重新构建，QEMU TCG、512 MiB、单核。
最终系统 `8fcd94339fdd58cc`，ISO SHA-256：
`56aaf05c2c8ef166bcdf067643e723a6d369ccc3adf0e63d02b7ceba8bbe19a8`。

```sh
python3 scripts/build.py --output-dir build/p0_deadline_system2
python3 scripts/build_ipc_deadline_probe.py --sdk build/p0_deadline_system2/sdk --output build/p0_deadline_fixture2
python3 scripts/build_ipc_exec_probe.py --sdk build/p0_deadline_system2/sdk --output build/p0_deadline_lifecycle_fixture2
python3 tests/ipc_exec_guest.py --system build/p0_deadline_system2 --fixture build/p0_deadline_fixture2 --output build/p0_deadline_guest2 --suite deadline --repeat 3 --serial-only
python3 tests/ipc_exec_guest.py --system build/p0_deadline_system2 --fixture build/p0_deadline_lifecycle_fixture2 --output build/p0_deadline_lifecycle_guest2 --repeat 3 --serial-only
python3 tests/kernel_process_wait_race_test.py --output build/p0_deadline_host_final
python3 tests/kernel_process_wait_race_test.py --sanitize --output build/p0_deadline_sanitized_final
```

| 检查 | 实际结果 |
|---|---|
| deadline guest | 3 轮，每轮 6 组全部通过 |
| 已由 sys50 确认 blocked 的 deadline worker | 6 timeout、9 ready、6 broken，全部符合预期 |
| 原生命周期 guest 回归 | 3 轮、9 调用、21 场景；33 个严格 broken 唤醒 |
| 生产 sys85 / timeout / revoke / process-wait host 提取 | 13 组通过 |
| 同一 host ASan/UBSan | 13 组通过，LeakSanitizer 未运行 |
| 每次客体后的资源 | 恢复 `[129806, 2, 0]` |

客体服务在超时期间真实存活且不收/不回对应消息。send 超时后服务实际收到原
payload，receive 超时后没有凭空生成消息。后续 ready 及 peer close 都先确认
worker blocked。0/past deadline、方向和 Files 范围拒绝、未知 mode、完整
64 位期限与无限期限分别测试。

host 提取的是生产 `case sys_ipc_wait`、`expire_waiters`、`revoke_ipc_channel`、
`wake_ipc_waiters` 和 `ready_with`。它用受控时钟在**同一截止时刻**分别先 close
和先 timeout，send/receive 两种方向各自只交付一次结果，timeout 不消费队列。
还测 0/过去/恰好到期的快速路径及 max-1/max 边界；Files deadline 的旧优先级
与 legacy 无限等待保持。只有时钟、调度、页表和无关设备边界由 host 替身提供。

首次扩展 host 提取器遗漏了生产前置声明中的默认参数，编译失败；补回相同声明
后普通及 sanitizer 通过，失败日志保留。新增测试后再次完整构建并重跑客体，
最终报告绑定最新源清单。公开 [摘要](../reports/p0_ipc_deadlines_20261127/summary.json)
保留原件和规范化副本摘要，平铺 manifest 绑定全部公开叶子。

## 交接与边界

网络模块可直接 `file_trap(85, endpoint, 5|6, absolute_deadline)`，或使用 SDK
wrapper。其 poll 超时、迟到 reply 只消费一次及有副作用 RPC 不重放由网络组合
资格单独证明。threading SDK 独立包、SMP、物理硬件与实时延迟上界未在本模块
验收。回退后新 mode 返回旧 invalid，消费方必须保留协商/有界回退，不能静默
恢复无限等待。第一模块的 exec 撤销及 blocked 唤醒修复仍保留。
