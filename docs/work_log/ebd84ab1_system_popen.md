# libc：system()/popen()/pclose()

2026-11-13。来源：账本 `PL-0007`（Lua `os.execute`/`io.popen` 不可用）。

## 实现

`src/user/libc/process_posix.cpp`，复用现有内核原语，不新增 ABI：

- shell 解析：`XOS_SHELL` → `/bin/sh` → `/usr/bin/dash`（C14：dash 在
  `/usr/bin/dash`，不自动装成 `/bin/sh`）。
- `system()`：`fflush(nullptr)` → `posix_spawn(shell, "-c", cmd)` → `waitpid`
  （EINTR 重试）→ 返回 wait 状态；shell 缺失返回 127。
- `popen()`：`pipe()` + file_actions `dup2` 到 0/1，`fdopen` 返回 `FILE*`；
  小表记录 `{FILE*, pid}`（上限 32）。
- `pclose()`：`fclose` → `waitpid` → 返回状态；未知 FILE* 返回 -1/`ECHILD`。

## 语义与边界

- 需要 spawn 权限：bare command / `tty-run` 启动的程序有；`exec-file` 没有
  （SL3 契约保持现状），失败经 `posix_spawn` 返回 `EPERM`。
- 没有信号投递：`system()` 子进程不注册进前台取消组，Esc 的取消不会中断它
  （等价于对 INT/QUIT 的忽略）；显式 kill 仍有效。
- 只支持管道流；`fork()` 语义仍是独立实验面。

## 验证

`tests/posix_shell_guest.py`（build `f2119e324f9d1401`，dash 导入 `/usr/bin/dash`）：

```text
true=1 exit3=1 missing=1 null=1 read=1 write=1
POSIX_SHELL_OK
resources_restored
```

覆盖 `system("true")`、`system("exit 3")`、`system("nosuchcommand-xyz")`→WEXITSTATUS 127、
`system(NULL)`、`popen("echo hi","r")`、`popen("read value; exit 7","w")`。
