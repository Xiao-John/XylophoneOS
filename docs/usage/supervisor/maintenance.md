# 维护工作会话与包恢复

2026-10-27。Xsh监督入口提供准入、文件写租约和持久恢复门禁，供xypm客体事务使用。

```text
maint-status
maint-run <program> [args]
maint-recover <recovery-program> [args]
maint-recover-boot
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
重新开放。xypm事务应使用`maint-recover-boot`，它使用系统内置的恢复程序，即使磁盘上的
xypm文件缺失仍可启动；也可使用`maint-recover /usr/bin/xypm recover`。

`maint-run`是Xsh的监督内建。dash是普通用户进程，在dash运行时不能满足“没有其他
应用”的条件；先exit回Xsh再执行维护入口。普通xypm list/info仍在两个Shell运行同一
程序、返回相同退出码，不增加dash的隐式监督权限或专用kernel包接口。

启动时检查`/var/lib/xypm/transaction`、`txdata`和`transaction_commit`；任一存在
或无法确认不存在时进入恢复门禁。读取和诊断仍可用；成功worker退出后重新检查，
必要时运行内置恢复器。损坏的材料会保留，不能通过删除标记代替恢复。

客体写命令示例：`maint-run /usr/bin/xypm install /out/package.xpk`、
`maint-run /usr/bin/xypm upgrade /out/package.xpk`、`maint-run /usr/bin/xypm remove ID`。
可为install/upgrade追加`--sha256`和预期摘要。当前验证不承诺任意断电或扇区撕裂安全。

[返回索引](../index.md)
