# `trace`

`trace`显示当前Xsh诊断模式；`trace on`开启详细进程/装载/等待日志，`trace off`
关闭正常生命周期刷屏。程序输出、非零退出、故障与取消始终可见。
该命令不改变构造权、程序行为或资源配额。只有bootstrap supervisor可设置内核
日志开关，普通程序和driver没有这项权限。

[返回索引](../index.md)
