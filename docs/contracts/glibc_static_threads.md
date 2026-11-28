# glibc 静态线程候选 profile

本页限定 XOS glibc G3-T 候选的接口行为，依赖 [原生线程契约](threading.md)
和 [glibc G2/G3 路线](../plans/glibc_port_scout.md)。验收结果与缺口见
[0c4c263f 工作记录](../work_log/0c4c263f_glibc_g3_static_threads.md)。

## 身份与生命周期

- 公开 `pthread_t` 保持原生不透明 TID；glibc 内部 `THREAD_SELF` 才是当前 TCB。
  公开句柄不转成指针。内核在 join 唤醒前可以回收线程 TLS/栈。
- `pthread_create` 完整初始化静态 TLS、DTV、TCB、入口与元数据后调用原生 start。
  线程返回和 `pthread_exit` 先做 TLS/TSD/libc 清理，再进入原生退出握手。
- 固定四项的线程名称/属性表由进程内锁保护，与内核每进程四线程上限一致。
  创建失败撤销登记；线程完成清理后删除登记；查询返回复制值，不保留 TCB 指针。
- `pthread_getattr_np` 为当前线程提供原生 stack bounds，为其他已登记线程提供
  创建时的 stack/guard 和后续 detach 状态。主线程的 guard 查询值为零；工作线程
  返回经过页取整、由保留映射间隙保证的请求值。退出后的查询返回 `ESRCH`。
- `pthread_gettid_np` 对存活且可由 `pid_t` 表示的身份返回 TID，否则返回 -1，
  保留 `errno`。全宽身份仍通过 `pthread_self` 获取。
- join/detach 的回收权由内核决定；join 保留完整 64 位返回值。非阻塞和定时 join
  仍返回 `ENOTSUP`，其输出保持原值。

## 私有同步与时间

普通、递归和错误检查互斥锁、条件变量、once、读写锁、barrier 和匿名 semaphore
使用 glibc 自身算法，等待/唤醒通过原生 process-private wait-word。

`CLOCK_MONOTONIC` 绝对截止时间直接转换为原生纳秒；`UINT64_MAX` 仅作无限等待，
有限值溢出返回 `EOVERFLOW`。无效纳秒返回 `EINVAL`，过去的截止时间返回
`ETIMEDOUT`。

`CLOCK_REALTIME` 使用现有内核固定的启动 RTC 偏移。先采样单调时间，再采样
实时时间；调度造成的采样间隔只能让换算值更早。原生等待报告超时后重新检查
实时时间，避免给调用者提前返回超时。未来若引入校时、暂停或其他偏移变更，
须重新验证该换算与等待生命周期。时钟失效等同步算法无法处理的错误终止进程，
保留真实失败。

`nanosleep` / `clock_nanosleep` 的正常、绝对和相对 elapsed-time 等待，以及
进程内按 PID/TID/sequence/deadline 定位的显式中断票据，见
[libc 定时等待契约](libc_timed_waits.md)。该扩展复用原生 wait-word；相对中断
返回剩余时间，绝对等待不改剩余时间输出。它不接受 pthread 取消投递。

## 明确拒绝的语义

| 请求 | 结果 |
|---|---|
| mutex/cond/rwlock/barrier 属性设置为 process-shared | `ENOTSUP`；属性原值保留 |
| robust mutex、优先级继承/保护协议 | `ENOTSUP`；属性原值保留 |
| `pthread_cancel` 投递请求 | `ENOTSUP`；不产生待处理取消 |
| 异步取消类型 | `ENOTSUP`；类型和输出原值保留 |
| deferred 取消类型 | 0；保持默认类型 |
| 非法属性枚举值 | `EINVAL`；属性原值保留 |

候选不接受取消投递，因此 glibc 的 cancelable condvar/semaphore 等待可使用同一
原生等待路径，不存在已接受却被丢失的取消。独立公开客体探针已验证
`pthread_exit` 的 cleanup LIFO、cleanup 先于 TSD，以及最后线程收尾。

共享等待、PI/requeue 等越过上述属性校验而进入内部未实现路径的调用仍触发明确
失败。动态 TLS、共享 libc 的线程创建、resolver/DNS、SMP、实时调度、完整信号和多线程 fork
继续按专门阶段处理。

## 活跃工作线程下的进程 exit

正常 `return`、`exit` 和 `quick_exit` 先通过 sys51 mode 1 领取唯一退出责任，
关闭线程创建并保留现存线程的调度和 I/O。所有者按 glibc 上游顺序执行调用者
TLS 析构、退出回调和适用的 stdio flush，最后由 sys_exit 统一停止并回收进程。
现存线程在窗口内 return/pthread_exit 时继续完成自己的 TLS/TSD/libc 清理；
仍在运行或等待的线程由最终进程退出回收，其应用析构需要应用主动协调。

同一所有者递归 exit 保留原生窗口，其他线程并发 exit 阻塞等待进程结束，不持有
glibc exit 锁。窗口为 30 秒绝对单调 deadline，超时退出 127 并记录内核跟踪事件；
无限持锁、回调环和退出所有者主动 pthread_exit 均发布明确失败。内核仅在回调
结束或失败后停止 peers。版本、权限、错误及旧 mode 0 兼容见
[线程契约](threading.md#有界进程清理窗口sys51-mode-1)。

每个工作线程仍在所有 TLS/TSD/libc 清理完成后以 release 递减计数，再执行原生
退出握手。最后线程收尾复用同一清理窗口和 glibc 回调路径。
本增量的 61 项实际客体结果、产物绑定和范围见
[8bfdcae1 工作记录](../work_log/8bfdcae1_glibc_active_process_exit.md)。
