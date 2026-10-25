# `exec-driver <path> [args...]`

从工作盘装载并等待一个工具驱动程序，同时显式授予它构造直接子任务的权限。
参数、ELF校验、前台Escape取消和结果报告与exec-file一致。

```text
exec-driver /bin/runtime_probe.elf driver
```

驱动可通过受限posix_spawn/waitpid运行子工具、收集退出码，并配置0/1/2。
该授权不继承给孙任务；普通exec-file/spawn-file不授予构造权。
驱动结束会清理未收集子任务及资源。权限机制不等于完整POSIX或fork。
详见 `docs/e08.md`。

此命令保留旧的一层构造权语义。因而`exec-driver /usr/bin/dash script.sh`可以让
dash启动普通子程序，但不能再把构造权委派给GCC；该路径会明确EPERM。需要运行
原生编译器的B1脚本，应从Xsh使用裸命令`dash script.sh`：Xsh为这个明确profile
配置深度2，dash再仅向用户态识别的GCC/G++ driver委派深度1。内核不识别dash、
GCC或路径。该有界委派不是通用Shell权限继承，详见`docs/dash_port_plan.md`。
