# `spawn-file <path> [args]`

与 exec-file 相同的流式文件装载，但启动后立即返回 `sup>` 和 PID。
随后用 `wait <pid>` 收集状态，或 `kill <pid>` 终止再 wait。文件会话独立于
supervisor；进程退出后回收端点、打开实例与未提交保存。
后台读取 stdin 会与终端竞争，尚无作业控制。见 `exec-file.md` 和 `wait.md`。
