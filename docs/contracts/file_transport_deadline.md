# Native files client 的绝对期限

`xos::file::client::set_deadline(ns)` 给后续每次调用设置绝对
`CLOCK_MONOTONIC` 纳秒期限；0 恢复既有入口行为，超过 `INT64_MAX` 拒绝且不
改变当前值。这是 SDK 类 API，不改变 files-v2 wire record、service status
或任何 syscall 编号。新头必须与同一 SDK 的 archive 一起使用。

## 一个会话、一条期限

原生无 libc 会话拥有者时，客户端在发送前检查时间，并将单次请求限制在
`min(调用者绝对期限, 当前时刻 + 5 秒)`。等待使用既有 sys85
`file_reply_until`，该模式只接受内核认证的 Files 回复端点。旧内核不支持
该模式时，每次最多睡至下一毫秒或期限，以单调时钟判定过期，不能以循环次数
推定时间。

glibc 拥有 FD/session 时，客户端调用新的 hidden C hook
`xos_file_session_exchange_until`，由同一个 G3 会话处理请求 ID、cwd/session
锁、startup 描述符初始化、发送、回复和失败锁存。有限期限同时传到 wait-word
和 Files reply wait；没有另外打开第二个早期会话或重置请求序号。

`transport_timeout = -1001` 是本地 SDK 结果，特意与服务既有 `-1..-16`
状态分离。回复中的状态仍必须属于服务状态范围，不能从 wire 注入这个本地
超时值。glibc 内部仍使用 `-ETIMEDOUT`，只在 native hook 边界转换。

在获得锁/发送前过期不会消费请求 ID，也不会毒化有效会话，调用者可重新给出
期限。请求发出之后超时或收到坏身份/短回复/未知服务状态时，同进程所有原生
client 共享不可恢复的失败状态；重建 client 或再次 `init()` 不会解除它。
glibc hook 同样使用 G3 的既有 poison，普通 libc I/O 也不能绕过失败。
进程退出由服务回收它持有的 open descriptions，不能在一个不确定的会话上
继续发“清理”请求并把迟到回复误认成新回复。

## 有限范围

没有 deadline 的旧原生调用保留既有兼容行为。已有 newlib 会话锁若没有提供
配套 `xos_file_session_lock_until`，有限期限调用返回 `not_supported`，不先
进入可能无限等待的旧锁。当前新lib线程锁尚未宣称获得该能力。glibc 的完整
exchange hook 已实现有限锁等待；原生单线程 loader 没有这种旧锁依赖。

这里不处理父子 ready、constructor 卡住、ELF 解析 CPU 预算、映射回滚或
exec 提交，它们必须继续共享启动的同一个绝对期限。测试使用生产客户端/G3
代码并注入内核边界；它不单独构成整个公开动态启动的客体资格。
