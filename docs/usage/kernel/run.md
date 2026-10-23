# `run`

- 控制台：内核调试控制台（`make run`）
- 需要彩蛋：否
- 语法：`run`
- 实现：`src/kernel/core/console.cpp` 调用 `tasks_start`；任务实现在
  `src/kernel/arch/x86_64/tasks.cpp`

## 行为

先输出 `[sched] event=starting`，再启动八个 ring3 任务并进入 100 Hz 的
round-robin 调度：

```text
[sched] event=starting
[sched] event=start tasks=8
```

启动后：

- `heartbeat` 每个时间片打印 `A`，用来说明定时抢占仍在工作。
- `spinner` 永不主动让出，只能被 IRQ0 抢占。
- `receiver` / `sender` 通过端点 1 收发 `ping`，成功时打印 `ping` 和 `tx`。
- `sender` 还会先测试超长消息和内核指针，分别打印 `bad length`、`bad pointer`。
- `probe` 先测试非法句柄和缺少发送权（`bad handle rejected`、`no send right`），
  再读取内核地址 `0x100000`，触发 task 级 page fault。
- `quitter` 打印 `bye` 后调用 `exit`，从运行队列消失。
- 启动过程本来就是一个多任务演示：按 `run` 后约 1 秒内旧演示任务会连续打印
  `A`/`ping`/`bad length`/`bad pointer`/`tx`，这不代表 `run` 失败。
- supervisor 出现后若约 1 秒没有输入，会自动停止旧演示任务
  1/2/3/4，并打印 `[sup] demo tasks stopped; prompt is sup>`；之后 `ps`
  只剩 supervisor 与 files。调试旧抢占/故障用例时可用 `demo keep` 禁止自动停止，
  `demo quiet` 手动立即停止。
- `supervisor` 是 C++ 用户态装载服务，提供 `sup>`：ps/kill/images/exec/spawn/wait/
  stats/primtest/elftest、ls/cat/stat/rm/edit/filetest/sync/exec-file/help。
  各条语法见 [监督终端索引](../index.md)。
  它能在旧 spinner 死循环旁继续响应，并可装载新的 ELF64 程序。

故障输出示例：

```text
[task] event=fault pid=5 vector=14 rip=0x0000000040000030 cr2=0x0000000000100000 result=killed
```

故障只终止 `probe`，heartbeat 与其他任务继续运行。
旧 heartbeat/IPC 演示输出会与命令回显交错，显示出来的 `A` 不会被当作用户输入。
想安静体验 ELF/文件命令，可在 supervisor 中分别 `kill 1`、`kill 3`、`kill 4`；
保留无输出的 spinner 仍可验证抢占。

## 失败与边界

- `run` 不返回内核调试控制台；执行后要回到内核控制台只能重启 QEMU。
- 停在 `xos64> ` 时不会出现 `A`/`ping`；如果一开机就持续刷 `A`，通常是在旧 QEMU
  窗口里，或串口上残留了之前会话的输入。`make run` 前先关掉旧窗口；需要安静
  时查看启动行里的构建 ID 是否与本轮 `make smoke` 一致。
- `sup>` 是最小监督/装载终端，不是完整 shell；文件是 FAT16 工作盘上的平铺
  8.3 短名，没有目录/管道/TTY 作业控制。
- 六个旧演示任务是平铺夹具，supervisor 与新程序用 SDK/ELF；模块来源仍是只读启动目录。
- 退出/被杀任务由下一次调度延迟回收；当前任务不会在自己的内核栈上释放自己。
- IPC 是单槽邮箱，满/空返回错误，没有阻塞等待或多消息队列。
- 没有 SMP、优先级、时间片配额；E04 创建/映射机制只授予初始 supervisor，不继承给普通程序。

## 相关

- 设计说明：`docs/architecture_and_boot.md` 的 E03 章节
- 验证：`tests/task_smoke.py` 与 `tests/process_smoke.py`
