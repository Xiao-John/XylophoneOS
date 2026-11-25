# glibc 终端适配 v1

范围：静态 glibc 的已授权 terminal v2 会话、startup v2/v3 接收、FD 生命周期、
termios 和有限 ioctl。生产协议继续使用 [terminal_control](terminal_control.md)，
不会把 glibc 的结构或 ioctl 数值发送给内核。实际实现与资格记录在
[e6b8c410 工作日志](../work_log/e6b8c410_glibc_terminal.md)。

## 授权、启动与对象

startup v2 的 terminal flag bit16 与非零 send handle 只指明待核验通道。
后端通过 sys81 枚举核对实际 controller、service peer、唯一双向端点及方向；
普通进程无法凭参数或 `.xos.tty` 标记取得权限。v2 要求三个 stdio 均关闭、
没有 file/path 重定向，再建立一个 kind5、handle0、O_RDWR 的终端对象，FD0/1/2
共享三个引用。`.xos.tty` v1 标记随真实后端对象链接，CRT 能力 bit1 表示终端。

startup v3 保持既有 24 字节 descriptor 与 offset176 的 terminal extension。
仅一个 kind5 对象可由多个 FD 引用，handle 必须为零、flags 为 O_RDWR；终端 flag
必须与存活终端对象一致，sequence 非零。先验证完整表和终端扩展，再连接通道及
执行已验证的 CLOEXEC cleanup。接收 native→glibc exec 时沿用原下一序号。
glibc 出站 spawn/exec/fork 的终端继承由进程模块在任何 transfer/create 前返回
ENOTSUP，直到完整序号、静默与失败事务契约落地。

共享 FD 后端持有实际对象引用，阻塞终端 I/O 前释放文件表锁；并发 close/dup2
不会把进行中的 I/O 路由到复用 FD。最后一个引用关闭两个通道。终端有独立
wait/wake 锁，每个会话一次一个请求；阻塞读期间其他终端操作按序等待，文件和
管道操作继续执行。用户需要读写同时进行时须先采用有限 VTIME 或独立会话模型；
本模块不承诺同会话全双工复用、pthread cancellation 或通用 select/poll。

## I/O 和模式

read/write 使用实际 terminal client 的 read_mode/write_until，单次最多 256 字节，
无 CR/LF 改写。默认 (VMIN,VTIME)=(1,0) 阻塞至数据，(0,0) 立即读取，(0,1..255)
限时读取；后两种零字节表示这次没有数据。非空 write 的零成功回复是协议错误。
未知/格式错误回复关闭会话，后续调用失败，不重连、不重放已发请求。

isatty(kind5)=1，fstat 为 S_IFCHR。普通 FD 按既有文件/pipe 路由；terminal 的
F_SETFL 若请求 O_NONBLOCK 则返回 ENOTSUP，flags 保持原值。

glibc 使用上游 generic GNU termios：四个 32 位 flag、20 个 8 位 c_cc、两个
32 位 speed，共 44 字节，speed 偏移 36/40；VMIN=16、VTIME=17。
tcgetattr 从服务读取真实模式，再逐字段构造 glibc 值。tcsetattr 完整校验后才
提交：iflag/oflag/lflag=0，cflag=CS8|CREAD|CLOCAL，双向 B115200，其他 c_cc=0，
VMIN/VTIME 为上述三个组合。原生 mode 的 32 字节布局仅在桥接层逐字段转换。

TCSANOW/TCSADRAIN/TCSAFLUSH 映射原生 now/drain/drain_flush_input；tcdrain
检查驱动发送完成，TCIFLUSH 丢弃服务规定范围内输入。TCOFLUSH/TCIOFLUSH 返回
ENOTSUP；非法 action/queue 返回 EINVAL；未知模式返回 ENOTSUP，原模式不变。
控制请求中断返回 EINTR，超时 ETIMEDOUT，通道/服务失效返回真实错误。

## libc 本地 ioctl 编号

这些编号属于此 glibc profile，参数按其公开 C 结构解释，不构成 Linux syscall ABI。

| 名称 | 数值 | 参数与行为 |
|---|---:|---|
| TCGETS | 0x5401 | struct termios*，同 tcgetattr |
| TCSETS | 0x5402 | const struct termios*，同 TCSANOW |
| TCSETSW | 0x5403 | const struct termios*，同 TCSADRAIN |
| TCSETSF | 0x5404 | const struct termios*，同 TCSAFLUSH |
| FIONCLEX | 0x5450 | 无参数，清除此 FD 的 FD_CLOEXEC |
| FIOCLEX | 0x5451 | 无参数，设置此 FD 的 FD_CLOEXEC |

无参数和未知 ioctl 不读取不存在的 vararg。未知请求对有效 FD 返回 ENOTTY，
无效 FD 返回 EBADF。窗口尺寸、FIONREAD、FIONBIO、job control、信号、规范模式、
回显及其他速率均未在此适配层实现。

## 验收要求

host 替换内核传输边界，覆盖真实客户端序号/格式/失效、v2/v3 恢复、模式转换、
dup/close lease、阻塞终端与其他 FD 的独立进展。真实 QEMU 使用 tty-run 授予的
terminal v2 通道，检查阻塞和限时输入、短写、tc/ioctl、跨 native exec 序号、
终端退出后下一应用复用和资源恢复。来源绑定 SDK、系统、fixture 与串口记录，
未运行项逐项保留。本轮 23 组 host、23 组 ASan/UBSan、六次真实终端客体及
三项既有 files 客体通过；一次 BIOS iso_read 启动失败与同源复跑结果同时保留。
活跃终端阻塞线程下正常 exit、客体服务死亡和完整上游套件待独立验收。
