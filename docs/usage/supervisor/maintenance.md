# 维护工作会话（P2-1）

2026-10-26。Xsh监督入口，供xypm后续客体事务使用；当前只交付准入和文件写租约，
尚不能在客体执行包install/upgrade/remove。

```text
maint-status
maint-run <program> [args]
maint-recover <recovery-program> [args]
```

只有监督任务和files服务仍存活时才允许`maint-run`，有后台或构造中应用返回busy，
不自动杀掉用户程序。会话只允许监督创建一个worker，且不授予其构造子进程的能力。
worker必须调用`file::Client::maintenance_acquire()`才能写文件；名字、路径、
包名及放进`/usr/bin`都不会授予维护权。正常应用不能直接取得控制权或释放写租约。

worker正常退出0后，监督等files收回所有打开实例/单文件staging、同步块设备，
然后释放准入屏障。非零退出、异常、Escape取消或清理失败则显示`retained`，保持
屏障；读文件/诊断仍可用，普通写入与新程序启动被拒绝。

保留会话用`maint-recover`启动一个显式选定的恢复工具。它重置旧worker/写租约时，
内核准入屏障始终保持；缺程序或恢复失败继续锁定，恢复工具退出0且清理成功才
重新开放。不要随意选择一个永远退出0的程序冒充恢复器。正式xypm恢复器还需P2-2
验证journal与归属，P2-1并未提供这个策略层。

`maint-run`是Xsh的监督内建。dash是普通用户进程，在dash运行时不能满足“没有其他
应用”的条件；先exit回Xsh再执行维护入口。普通xypm list/info仍在两个Shell运行同一
程序、返回相同退出码，不增加dash的隐式监督权限或专用kernel包接口。

P2-1会话是本次启动内状态，不承诺重启恢复或任意断电安全；完整包写命令未开放。
下一批必须先实现持久journal、备份、恢复门禁，再向用户提供这些命令。

[返回索引](../index.md)
