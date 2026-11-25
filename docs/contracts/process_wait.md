# Native process wait and wait-any

2026-11-25 · 此扩展保持 syscall 20 和 48 字节 `process_status` 的既有 ABI，
为 glibc/dash 提供由内核认证的任意子进程等待。它不使用 libc PID 缓存。

## 请求与结果

`sys_process_wait(first, status_address, flags)` 的 flags 定义为：

| flags | first | 行为 |
|---:|---|---|
| 0 | 精确 PID | 原有阻塞等待 |
| 1 (`process_wait_nonblocking`) | 精确 PID | 原有非阻塞等待 |
| 2 (`process_wait_any`) | 必须为 0 | 等待任一已启动的直接子进程 |
| 3 | 必须为 0 | 非阻塞查询任一已完成的直接子进程 |

未知 flags、wait-any 配非零 first 返回 `process_error_invalid`；未设置
wait-any 的 first=0 保持原有拒绝行为。新 helper `sdk::wait_any` 显式选择
该扩展，旧 `sdk::wait` 调用形态和精确 PID 语义保持。

成功返回 0，并将真实 PID、正常退出/故障/kill outcome、code 及诊断字段写入
既有 `process_status`。无可等待直接子进程返回 `process_error_denied`；
存在子进程但非阻塞调用无可领取完成记录时返回 `process_error_would_block`。
所有失败保持用户输出原值。building 构造体在 start 前不进入 wait-any 可见范围。

## 所有权与生命周期

- 内核按调用者真实 PID 匹配完成记录的 parent；其他应用无法等待或消费该记录。
- 已登记的精确 PID waiter 保持完成记录的优先领取权。wait-any 从尚未被领取的
  ready 记录中选择一个，并将等待者绑定到该真实 PID；唤醒到 copyout 的间隔
  仍保留领取权。多个等待者不会重复交付同一个完成记录。
- 消费只发生在有效 copyout 之后，同时计入父进程 child CPU 一次。copyout
  失败释放等待者的 pin 和领取权，完成记录可由其他等待者重新领取。
- 最后一个子进程被另一线程消费后，仍阻塞的 wait-any 唤醒并返回无子进程。
  父退出/cancel 的既有回收路径撤销等待和 pin；普通父退出后的已启动子进程
  继续归内核 reaper，building 子进程仍取消。
- 成功 exec 保持同一 PID 及现有完成记录，替换后的应用仍可 wait-any 回收旧
  镜像创建的子进程。失败 exec 保持原等待和子进程状态。

本扩展提供 direct-child 语义；进程组等待、stopped/continued 和信号投递留给
独立契约。现有精确 PID 的重复阻塞等待仍返回 `thread_error_busy`。

## 验收要求

生产 `tasks.cpp` 的 syscall、finish 和 deferred copyout 宿主提取测试覆盖
exact/any 竞争、多个 waiter、非阻塞、错误输出、building 隔离、故障/kill、
copyout 失败归还、最后记录消费和 pin/CPU 回收。真实新系统与原生用户态 fixture
覆盖阻塞唤醒、并发唯一消费、exec 后既有子进程和资源回基线；实际结果由独立
报告记录，构建本身不满足客体验收。
