# `exec-file <path> [args]`

在 `sup>` 从工作盘装载静态 ELF，并等待结果。先打开并保持读锁，读取有界 ELF
header/PHDR，逐段逐页读取与映射，清零 BSS；关闭源文件成功后才启动子任务。
文件在读取期间不能被写打开/替换，失败关闭并回滚所有构造资源。

文件不再受 128 KiB 启动模块上限限制；最多 65536 用户页（含栈），同样检查
入口、范围、对齐、W^X，拒绝动态链接等未支持特征。例：

```text
exec-file /bin/example.elf arg
```

显示实际 PID、退出/故障/终止状态。前台等候可单独按 Escape 取消。命令按空格
分词，无引号；SDK 可处理含空格的路径，但终端暂不能表达它。
机制见 `docs/e08_storage_and_sessions.md` 与 `docs/e08_runtime.md`。
普通exec-file不赋予程序构造子任务的权限；工具驱动使用exec-driver。
