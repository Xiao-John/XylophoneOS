# 公共线程：实现摘要

截至2026-10-27。语义以[线程契约](../contracts/threading.md)和[实现](../implementation/threads.md)为准。

## 实现

- 1:1内核线程，单核PIT抢占；进程拥有地址空间/文件会话/权限/完成记录，线程拥有TID、
  上下文、内核栈、FS/TLS/FPU和等待状态。8进程、每进程4线程、全局32槽；256MiB用户页预算。
- create/start/abort、join/detach、正常与强制退出仲裁；死线程栈及时回收，join结果按约定消费。
- wait_word/wake_word用进程身份+对齐地址，无丢失唤醒；单调deadline、阻塞sleep、退出出队。
  有等待者的映射释放busy边界仍需未来VMA设计协调，不冒称完整munmap。
- pthread mutex/cond/once/TSS，线程newlib reent/errno、stdio/堆锁、环境同步和静态TLS析构；
  C++线程/异常/运行库专项与普通SDK隔离，旧冻结SDK不覆盖。
- 修复PT_TLS模板对齐与TP对齐混用、FPU夹具编译配置和日志兼容；具体回执保留真实失败。

## 证据与边界

T0–T2冻结基线9c896df，78组客体检查，完整系统/SDK/工具/源摘要见
[qualification](../reports/threading_20261025/qualification.json)。公开回执规范化本机路径时
保留原始/公开副本摘要；不能由公开路径变化推定旧字节相同。

T3-PY真实pthread/GIL见[用户态摘要](userland.md)，T3-QT未运行；没有SMP、完整pthread取消、
rwlock、atfork或线程profile fork/exec资格。CLOCK_REALTIME的后续0058结果单列，不追改T1。

## 合并来源

原文按[source_index.json](source_index.json)记录的提交、路径和SHA256恢复；以下锚点保留旧引用。

<a id="log-0031_threading_contract"></a>
- `docs/history/threading.md#log-0031_threading_contract`
<a id="log-0036_thread_pr_baseline"></a>
- `docs/history/threading.md#log-0036_thread_pr_baseline`
<a id="log-0037_threading_t0_t2"></a>
- `docs/history/threading.md#log-0037_threading_t0_t2`
<a id="log-0041_threading_local_merge"></a>
- `docs/history/threading.md#log-0041_threading_local_merge`
