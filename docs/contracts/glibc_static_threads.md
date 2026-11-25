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

G2 候选以 acquire 读取 `__nptl_nthreads`。大于 1 时通过原生 console 诊断并
以状态 127 强制终止，避免停止持有 malloc/stdio 锁的线程后再进入普通 libc 收尾。
这是当前实现的能力边界；活跃工作线程下的正常 `exit` 回调/flush 仍待独立闭环。

本模块在所有 TLS/TSD/libc 线程清理完成后，以 release 递减线程计数；后续只执行
原生退出握手。全部 join 后的正常退出、主线程 `pthread_exit` 和最后工作线程
收尾已在独立完整 SDK 上各通过三轮客体验收。定向负向探针让工作线程持有 stdout
锁，检查状态 127、原生诊断和资源恢复；具体 SDK/镜像及日志散列见工作记录。
