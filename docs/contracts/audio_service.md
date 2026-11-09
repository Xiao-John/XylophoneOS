# 用户态单音服务协议 v1（AU2）

2026-11-09。实现复用 sys82 resource 2、sys86 命名 IPC 与普通进程生命周期；不增加
syscall、设备号或设备协议编号。协议头在 `src/shared/include/xos/audio_abi.hpp`，SDK
客户端在 `src/user/include/xos/audio_client.hpp`。

## 身份与所有权

- bootstrap supervisor 从内嵌可信镜像启动 `audio_service`，通过 sys82 `delegate=6` 给它
  单一、不可再委派的扬声器 controller 权限；授权不依据镜像名或 IPC 名称。
- 服务在用户态发布 `xos-audio`。IPC 内核认证连接发送者；服务查询对端 PID，只为每个
  PID 保留一个 session，最多 8 个不同 client PID。client 不获得 PIO。
- 服务为每个 tone 创建无 spawn 委派权的子进程，并由 controller 将固定 Speaker PIO
  授予该 building 子进程。worker 仅持有 `0x42`、`0x43`、`0x61`，单次租约
  上限 2,500 ms（最长音符 2,000 ms + 500 ms 调度余量）。服务本身无 Speaker PIO；worker 每个音符后退出或主动 release。
- 任一时刻整个系统最多一个活动序列；竞争提交返回 `process_error_busy`，不排队。
  请求者退出时 IPC 端点失效，服务取消该 session 的活动序列。服务退出、被杀或故障时，
  内核撤销 controller、终止子 worker 并静音；supervisor 自动重启服务。重启不恢复旧
  session/job，也不自动重播。

## Wire 格式与约束

IPC 单条消息上限 4,096 字节。v1 request 固定 544 字节：`version=1`、`size=544`、
`operation`、`note_count`、`job_id`、64 个 `{frequency_hz,duration_ms}` 音符和零保留字段。
response 固定 48 字节，包含版本/长度、状态、完成音符数、错误、job ID 与能力上限。
未知操作、错误尺寸、非零保留字段和未使用音符槽非零均拒绝。

提交一次携带完整序列；服务完整校验后才受理，因此坏序列不会播放前缀：

- 1–64 个音符；频率 `0` 表示 rest，非零频率为 40–5,000 Hz。
- 每项 10–2,000 ms；所有项时长之和不超过 10,000 ms。
- PIT 输入频率 1,193,182 Hz；用户态驱动四舍五入计算 channel 2 整数 divisor。
- 首次请求 `capabilities` 返回并核对冻结上限。`submit` 成功立即返回 `accepted` 和
  服务单调递增 job ID；唯一活动序列时返回 busy。
- `status(job)` 查询当前 session 最近一次 job，报告 accepted、playing、completed、
  cancelled、expired 或 device_lost；completed_notes 只统计已完成的音符/rest。
- `cancel(job)` 只影响同一 session 的匹配 job。服务按请求顺序线性化竞争：已完成的
  job 返回 completed；活动 job 同步杀死 worker、触发内核 stop 后返回 cancelled。
  重复 cancel 查询稳定终态，不触碰后续新 job。
- `close` 关闭 session 并取消其活动任务。IPC send/receive 使用系统单调 deadline，单次
  client 操作最多等待 1 秒；超时使本地 channel 失效并返回真实错误，提交结果可能未知。
  SDK 不自动重连或重播。服务重启后需显式建立新 session，旧 job ID 不可跨服务代次使用。

服务仅保留每个 session 的最近 job 终态；该 session 再次 submit 后旧 job ID 失效。job ID
耗尽时服务拒绝新任务而不回绕。客户端给自己保存的 job ID，不把 PID 或文件名放入 wire
作为身份依据。

## Shell 入口

- `tone <Hz> <ms>`：异步提交单音，输出 job ID；例如 `tone 440 250`。
- `melody <file>`：先读完整文件、校验全部行，再提交。文件为 UTF-8/ASCII 兼容纯文本，
  每行两个十进制整数 `frequency_hz duration_ms`，以 LF 或 CRLF 分行，允许最后一行无
  换行；空行、注释、额外字段和大于 2,048 字节的文件拒绝。`0 duration_ms` 是休止。
- `audio status <job>`、`audio cancel <job>`、`audio close` 操作 supervisor 当前
  session。`audio start` 可启动服务；`audio restart` 杀死并重启服务，所有旧会话失效。

全局 mute/unmute、音量、混音、持久 job 历史、文件流式解析及 WAV 均不属于 AU2。cancel
和服务退出是静音路径；纯方波不暴露百分比音量。QEMU WAV capture 证明仍须结合客体权限、
退出和调度测试；无真实捕获/客体资格时不声称 AU2 已通过。
