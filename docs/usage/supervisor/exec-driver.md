# `exec-driver <path> [args...]`

从工作盘装载并等待一个工具驱动程序，同时显式授予它构造直接子任务的权限。
参数、ELF校验、前台Escape取消和结果报告与exec-file一致。

```text
exec-driver /bin/runtime_probe.elf driver
```

驱动可通过受限posix_spawn/waitpid运行子工具、收集退出码，并配置0/1/2。
该授权不继承给孙任务；普通exec-file/spawn-file不授予构造权。
驱动结束会清理未收集子任务及资源。权限机制不等于完整POSIX或fork。
详见 `docs/e08_runtime.md`。
