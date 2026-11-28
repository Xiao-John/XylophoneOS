# P0 通用权限与进程生命周期组合验收

2026-11-27；基线 main `daf2bd24ce92525ce61054ebe585ab0e88ed06e4`。
本模块修补 PR #158 的确定性阻塞验收缺口，并复用现有机制检查委派、撤销、
服务重启、配额回收和 process wait。生产 syscall 与内核行为保持原契约。

## 问题与实现

原 exec fixture 在通知 child 替换后才进入 `ipc_wait`，并同时接受 broken 和
denied。child 可能在 parent 登记等待前完成 exec，因此通过不能证明阻塞唤醒。
现在 parent 的 native worker 单独进入等待；主线程用既有 sys50 观察本进程
恰有目标 worker 阻塞，再触发 exec，join 后仅接受 `ipc_error_broken`。
旧 child 保持单线程。没有增加调试 syscall、定时猜测或内核测试分支。

同一 fixture 增加五条终止路径：owner revoke、peer close、正常退出、fault、
parent cancel。各路径同时确认空队列 receive 和满队列 send 两个 worker 已阻塞，
逐一验证 broken。随后用户态重启同名服务，验证新 PID、新 token、旧 token
仍拒绝、旧 pending 连接已清除和真实往返。显式关闭还验证 peer 进程仍存活。

权限组合包括创建能力默认不继承、跨 PID 借用句柄拒绝、delegate 只能缩权、
合法再次委派、manage/receive 越权拒绝、内核 badge、reply token 只消费一次、
owner close 撤销派生引用，以及 sys88 每进程 handle 额度失败和回收。

构建器单独编译机制级 native thread core，并绑定源码和 SDK 摘要；不把
single-thread libc 变成线程 profile。runner 冻结系统及 fixture receipt 原始身份，
开始和结束均重新核验，防止中途替换自洽产物。

补跑原有 process wait host gate 发现主线测试已不能编译：`finish_task` 新增
Files 退出唤醒依赖，但提取器缺少端点记录和唤醒实现。现补全真实 `ready_with`
与 `wake_ipc_waiters` 的提取，新增 Files 死亡只唤醒对应回复接收者的检查。
设备/显示清理继续为该 host 测试范围之外的替身，未用替身覆盖目标唤醒逻辑。

## 开发环境与输入

全部构建及运行使用已校验的 **XOS SDK Preview 2 Linux x86-64**，经其原有
Bubblewrap launcher 执行。预览包内 sysroot 来自 `498a40ce`、build
`152cd96f4d4e95ab`；本次用其 GCC 16.2.0、Binutils 2.47.20260726、NASM 3.02
重新构建当前源码系统与配套 SDK，没有用预览包旧 ISO 宣称当前内核通过。
使用常规 launcher，不声称 offline 网络隔离。客体采用 QEMU TCG、512 MiB、单核。

最终系统 build `74c2dc2b7d2a8c2a`，ISO SHA-256：
`8ac9f8d8c0491600bca80dc4b2975b08e959cd66a066b14f669dfed997a29758`。
fixture 为 native freestanding 程序，不链接 libc。

在 SDK launcher 内执行：

```sh
python3 scripts/build.py --output-dir build/p0_lifecycle_system3
python3 scripts/build_ipc_exec_probe.py --sdk build/p0_lifecycle_system3/sdk --output build/p0_lifecycle_fixture3
python3 tests/ipc_exec_guest.py --system build/p0_lifecycle_system3 --fixture build/p0_lifecycle_fixture3 --output build/p0_lifecycle_guest --repeat 3 --serial-only
python3 tests/process_wait_any_guest.py --system build/p0_lifecycle_system3 --output build/p0_lifecycle_wait_guest --repeat 3
python3 tests/kernel_process_wait_race_test.py --output build/p0_lifecycle_wait_host2
python3 tests/kernel_process_wait_race_test.py --sanitize --output build/p0_lifecycle_wait_sanitized
```

## 实际结果

| 检查 | 结果 |
|---|---|
| IPC exec / lifecycle / authority | 3 轮、9 次调用、21 个场景全部通过 |
| 真实已阻塞的 IPC 唤醒 | 33 个 worker 均严格返回 broken |
| wait-any 现有完整定向 guest | 27 次运行、10 组语义全部通过 |
| 生产 process wait/finish 提取 host | 9 项通过 |
| 同上 ASan/UBSan | 9 项通过；LeakSanitizer 未运行 |
| 每次 guest 调用后的资源 | 均恢复 `[129806, 2, 0]`：页、进程、完成记录 |

wait-any 继续覆盖精确/任意竞争、唯一消费、失败 copyout 归还、building 发布、
fault/kill 身份、exec 保留旧子进程、orphan 与 foreground cancellation。
本轮没有新增进程权限 ABI，也不将 UID/DAC 设计当作已实现功能。

首次 fixture 编译误用了不存在的 `wait(..., true)` 重载，改为既有 nonblocking
sys20；原 host gate 的编译失败也保留。最终完整系统在这些修正后重建，旧构建
没有绑定到通过报告。原始日志保存在 `build/`，公开派生副本替换环境路径，
文本日志统一 CRLF 与终端行尾空白；原件摘要保持在 summary。

证据：[组合摘要](../reports/p0_lifecycle_20261127/summary.json)、
[IPC 客体](../reports/p0_lifecycle_20261127/ipc_guest.json)、
[wait 客体](../reports/p0_lifecycle_20261127/wait_guest.json)。平铺 manifest 绑定所有
公开叶子，summary 同时保留原件与派生副本摘要。

## 下一模块与边界

sys84–86 只有全局池，尚缺每 PID 的 pair/name 公平额度；独立下一模块实现与验收。
sys88 已有 per-process 额度，本次验证其失效/回收，不宣称完整进程树预算。
服务重启必须重新认证并建立会话；已交付业务请求仍可能结果未知，没有承诺透明恢复。
sys81 继承压力、完整终端/显示/Interactium 应用回归、SMP 和物理硬件未在本模块运行。
回退本模块只撤回测试与文档，生产内核、SDK wire ABI 和旧资格不变。
