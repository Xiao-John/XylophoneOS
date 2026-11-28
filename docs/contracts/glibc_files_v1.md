# glibc G3-F：files 后端与 FD 生命周期

状态：静态 glibc 研究 profile 的文件模块；实现与宿主集成测试已交付，
真实客体验收由本组公共 API fixture 和组合 SDK runner 执行。
G2 提供完整静态 libc、CRT、主线程 TLS 与启动参数入口；G3-T 提供线程运行时。
本契约沿用 [files identity](file_identity.md)、
[文件元数据](file_metadata_v1.md)、[ABI 登记](abi_registry.md) 的现有协议。

## 公共接口与数据布局

glibc 的 `open/open64/openat/openat64`、`read`、`write`、`writev`、
`close`、`dup/dup2`、`fcntl/fcntl64`、`lseek/lseek64`、
`fstatat/fstatat64`、`fsync`、`ftruncate/ftruncate64`、`isatty`、`unlink`
进入 `xos_file_runtime.c`。上游的 `fstat/stat/lstat` 通过 `fstatat`，
stdio 通过这些真实文件操作访问 files 服务。

内部桥返回负的 glibc errno，由公共 wrapper 写入线程自己的 `errno`。
实现只依赖公开 XOS 服务协议、启动 ABI 和原生系统调用；没有 newlib 私有
结构、符号或宿主 Linux syscall fallback。

`bits/fcntl.h` 保留现有启动快照所使用的 XOS 公共 flag 数值。
`bits/stat.h` 定义本 glibc profile 的 LP64 布局：`stat/stat64` 均为 120 字节，
inode 与 offset 为 64 位，三个 timespec 保留纳秒字段。这是 libc 结构布局，
files 消息布局与内核 ABI 保持现状。编译断言位于 `files_public_layout.c`。

FAT 的权限和时间投影遵循文件元数据契约：创建 mode 由服务的固定权限规则
解释；uid/gid 为 0，nlink 在延迟删除时为 0；mtime 同步投影到三个时间字段。
旧服务的空 metadata trailer 可接受，已提供的 FMET v1 trailer 必须严格有效。
当前 identity 是服务定义的 16 位命名空间：根 1、FAT 2–65533、`/dev` 65534、
`/dev/null` 65535。零 identity 和超界值作为协议错误处理。

`access` 的存在性与读写权限来自同一次 stat 的元数据。`X_OK` 同时请求
[files 可执行文件查询](file_identity.md#可执行文件查询)，并要求成功响应中的确认位。
客户端无需打开远端句柄，旧服务省略确认位时返回 `ENOTSUP`。

## FD、并发与服务会话

每进程有 32 个 FD 和 32 个本地 open-description 记录。普通文件句柄的实际
并发上限由 files 服务的 16 handle 配额决定。`dup` 与 `dup2` 引用同一个记录，
因此共享服务侧 offset；CLOEXEC 则属于各个 FD。独立 `open` 保持独立 offset。

`getdtablesize()` 和 `getrlimit(RLIMIT_NOFILE)` 从 FD 表使用的同一私有容量常量
返回 32，后者的 soft/hard 值均为 32；上游 `getrlimit64` 转接得到相同结果。
文件、console、terminal、pipe 和 socket 共用此表，不按打开对象种类另算配额。
查询不修改限制、不新增 syscall，也不扩大 files 服务独立 open-description 的配额。
其它有效资源种类返回 `ENOSYS`，无效种类返回 `EINVAL`，失败不覆盖输出；
`getrlimit` 的空输出指针返回 `EFAULT`。`setrlimit` 保持未实现，`sysconf` 的其它
能力不由本次资源查询推定。真实 FD 耗尽与 gnulib 消费者由
`tests/fixtures/gnulib/consumer.c` 和 `tests/gnu_gzip_guest.py` 验证。

一把进程私有锁串行化完整 request/reply 与文件 FD 变更；等待使用现有
`sys_wait_word/sys_wake_word`。请求序号严格递增，溢出后返回错误。
普通文件 read/write 各提交一次有界请求，最大分别为 3798/3800 字节，
大请求向调用者返回真实短 I/O，stdio 可以继续消费余量。

console/pipe 阻塞 I/O 在保留 open-description 引用后释放该锁，避免阻塞所有
其他文件操作。并发 `close` 立即释放 FD 号码，最后一个 I/O lease 完成后才
关闭底层 route；新打开的同号 FD 不会被旧请求关闭。

`writev` 聚合最多 4096 字节后执行一次后端调用。管道总长不大于 PIPE_BUF
时通过原生 atomic 标志一次提交，并按完整长度等待空位；普通文件仍遵守
3800 字节 wire 容量。O_APPEND 在服务侧执行，不用客户端 seek+write 模拟。

`close` 错误仍移除本地 FD，重复 close 返回 EBADF。`dup2` 先保留源描述再
替换目标，目标旧描述的最终关闭错误不撤销已完成的替换。

## 原生匿名管道

`pipe` 和 `pipe2` 使用现有内核管道，在同一 FD 锁下登记读端和写端。
`pipe2` 接受 `O_CLOEXEC` 和 `O_NONBLOCK`。描述符不足返回 `EMFILE`，
原生管道配额耗尽返回 `ENFILE`，失败时保留调用者的输出数组。
`dup` 产生的别名共享方向、缓冲区和 `O_NONBLOCK`，各自持有 `FD_CLOEXEC`。
写端最后一个引用关闭后，读端先排空剩余数据再返回 EOF。读端最后一个引用
关闭后，写端返回 `EPIPE`。当前原生信号 profile 不在该路径投递 `SIGPIPE`。

`PIPE_BUF` 为 4096 字节。阻塞写入按需等到完成，期间保留并发 I/O 引用。
非阻塞写入不大于 `PIPE_BUF` 时要么完整写入，要么返回 `EAGAIN`；
更大的非阻塞写入可以短写。原生管道操作不依赖 files 会话。

出站 `posix_spawn` 跳过额外的 CLOEXEC 描述符，保留父进程描述符。
启动快照持有有向管道引用直至提交或撤回。加载器用现有 `sys_process_stdio`
把读端挂到子进程 fd 0、写端挂到 fd 1 或 2。方向不符、非阻塞管道和额外的
非 CLOEXEC 描述符返回 `ENOTSUP`。

普通及封存文件经已有 files 句柄转移进入子进程的 0/1/2。每次转移持有同一
打开描述，保留服务侧位置和追加行为。加载器只向带现有 `.xos.exec` 标记的
接收端转移文件，否则返回 `ENOTSUP`。父进程在加载期间保留原始引用。

## 定位读写与目录流

`pread/pread64/pwrite/pwrite64` 使用独立 `xos_file_positioned.c` 与 files op
30/31。请求 `handle` 为调用者文件句柄、`offset` 为绝对位置、`length` 为实际
有界传输量，其余控制字段为零。read_at 的成功响应 `value == length`；write_at
返回真实已写字节、空 payload。每个请求在服务中串行完成，成功、短 I/O 和失败
均不改打开描述的 position。跨进程 shared description 由服务保证；客户端不
执行 seek/read/restore。O_APPEND 不改变 pwrite 的显式位置。

公开调用仍一次最多读 3798/写 3800 字节，较大请求返回真实短 I/O；零字节写
不增长文件。offset 为负返回 EINVAL，超过当前 FAT 可表示范围 0xfffffffe
返回 EOVERFLOW；非文件 route 返回 ESPIPE。权限、目录错误、维护门禁、空洞
零填充、部分进度和回滚规则与普通文件 I/O 共用。旧服务未实现 op30/31 时返回
确定错误，禁止以 seek/read 模拟缺失的跨进程语义。

`opendir/fdopendir/readdir/readdir64/readdir_r/readdir64_r/closedir/dirfd/rewinddir/`
`telldir/seekdir` 使用 op 2 的 list_identity 格式，细节见文件身份契约。
上游 scandir/scandir64 和排序逻辑复用这些真实目录接口。公共 dirent/dirent64
保留原 generic 字段前缀，name 数组固定 256 字节；x86-64 LP64 下均为 272
字节，d_name offset=12，d_ino 为真实服务身份。原目录入口是未实现 stub，本次
启用时一并冻结有界结构，调用者须使用候选 SDK 成套重建。

每个 DIR 持有一个 FD、一份 open-description lease 和最多 3798 字节缓存页；
opendir 设置 CLOEXEC，fdopendir 只在成功时接管传入 FD，失败保留调用者所有权。
closedir 关闭 FD 并释放 lease。单个流的推进、复制型 readdir_r 和 cookie 操作
由私有 wait-word 锁串行化；不同流可并行。同流 readdir 返回的内部指针会被后续
调用覆盖，调用者需要并发保留条目时应自行复制或使用 readdir_r。

EOF 返回 NULL 并保留 errno；调用前设 errno=0 后，NULL/0 是正常结束，
NULL/非零为错误。readdir_r 通过返回值报告错误。rewinddir 丢弃已缓存页面，从
实时目录开头重新读取。无法恢复传输的错误仍由共享会话 fail latch 处理。

## 协议校验与服务死亡

IPC endpoint 来自当前进程的 `sys_ipc_handles`（sys22）。每次操作使用单调时钟的
5 秒绝对截止时间。遇到空队列，用 sys85 的 `file_reply_until` 模式在当前进程
的认证文件回复端点等待。唤醒后用原截止时间重新接收并校验回复。
旧内核以 invalid argument 拒绝此模式，运行库仅在该结果下保留原先的 1 毫秒
睡眠重查路径。其他等待错误沿会话失败路径处理。

必须匹配完整 4096 字节 reply、magic/version、request_id 和已知状态码。
成功 reply 还校验对应操作的 handle、flags、length、value、identity 和 metadata
形状。read 的 value 必须等于实际 length，write 不得超过提交长度或对非空请求
返回零字节成功。不得使用未验证的长度复制数据。

发送失败、服务死亡、超时、时钟错误或协议畸形会终止当前 files 会话。
超时首次返回 ETIMEDOUT，其他协议/运输失败返回 EIO；后续文件 RPC 固定返回
EIO，不重连、不重放旧操作。超时前的写入可能已经提交，因此不能自动重试。
console/pipe 保持各自独立 route，可输出诊断并退出。进程销毁仍由既有服务会话
回收逻辑收回远端资源。

## 启动继承

G2 CRT 在进入 glibc 前设置 hidden `__xos_startup`。文件后端惰性读取，先验证
startup 映射范围、对齐、magic、version、扩展长度、flags 与保留字段。
hidden 常量 `__xos_file_startup_capabilities` 的 bit0 表示链接了本接收后端，
bit1 表示已链接真实终端后端；本组合值为 3，CRT 可用 weak 引用识别这些能力。
G2 基础 console profile 仍可单独链接。终端 startup v2/v3、kind5 与授权检查见
[glibc 终端契约](glibc_terminal_v1.md)。

- v1：接收 0/1/2 标准 route。
- v2：接收 loader 已授权转移的文件句柄和关闭 mask，不重新按路径打开。
  重复转移 handle、非法 flags、孤立字段和未支持的路径重定向显式失败。
- v3：接收最多 32 项描述快照；相同 object 的 aliases 共享一个记录。
  先验证整张表，再执行 CLOEXEC-only 清理项；重复 FD、重复 cleanup、同一个
  handle 的多个 ownership 记录，以及 cleanup/live 重叠均拒绝。
  存活 FD 的 CLOEXEC 位已清除，唯一 CLOEXEC 描述在接收端关闭。

工作目录仍由 loader/files 服务维护的 identity 继承。普通 `posix_spawn` 使用
既有加载器与启动 v2。需要接收转移文件的 glibc 程序须单独声明 `.xos.exec`，
例如[重定向验收程序](../../tests/fixtures/glibc_g3/dash_stream_child.c)。

## 明确支持范围

`F_GETFD/F_SETFD/F_DUPFD/F_DUPFD_CLOEXEC/F_GETFL` 支持；`F_SETFL` 可变更
本地 O_NONBLOCK；终端对象请求该标志返回 ENOTSUP 并保持原 flags。改变
O_APPEND 返回 ENOTSUP（既有服务没有该句柄操作）。
文件系统无 symlink，NOFOLLOW 和 AT_SYMLINK_NOFOLLOW 按此 profile 处理。
相对路径的 `openat/fstatat` 支持 AT_FDCWD；其他 dirfd 相对路径返回 ENOTSUP。
`fstatat/fstatat64` 接受 GNU 兼容查询位 `AT_NO_AUTOMOUNT`，通用 `statx`
将其转交给 `fstatat64`。XOS 无自动挂载，置位时照常查询元数据。未知标志位仍返回 EINVAL。
`AT_EMPTY_PATH` 可查询已打开的 FD。未知操作返回确定错误。

静态单线程 glibc 的 `fork` 和 `_Fork` 复用原生进程快照和文件服务
`clone_session`。内核和 files 分别保留 FD 指向的 pipe 及打开描述，files 确认后
子进程才可运行。子进程重新取得自己的认证端点和请求序号，保留原工作目录、FD
标志与共享偏移。带终端对象时还须登记原对端派生的子通道，由子进程重新认证。
原生快照、终端登记和 files 确认共用同一个 5 秒单调截止时间。超时的父进程撤销
未启动的子进程。子进程继承调用线程的名称和栈信息，并以自己的 TID 对外报告。
创建权、深度和回收语义沿用现有 ABI。共享 libc 和启用线程的进程继续显式拒绝。

子进程按路径打开的启动重定向、文件锁、mmap 文件映射、glibc 出站 exec 及
异步取消暂不属于本模块。fsync 调用真实 files sync，其他尚未实现操作返回明确错误。

## 验证入口

```sh
python3 tests/glibc_g3_files_host.py --output build/glibc_g3_files_host
python3 tests/glibc_g3_files_host.py --sanitize --output build/glibc_g3_files_sanitize
python3 tests/glibc_files_extra_host.py --output build/glibc_files_extra_host
python3 tests/glibc_files_extra_host.py --sanitize --output build/glibc_files_extra_sanitize
python3 tests/glibc_static_guest.py --system-build build --glibc-build build/glibc-c --suite pipe --output build/glibc_pipe_guest
```

宿主回归替换内核陷阱而保留生产 FD/IPC 状态机，覆盖故障注入、并发、继承、
管道 lease 和原子写；另一组链接实际 `files.cpp`/FatFs，验证真实文件服务。
这两类报告分别标明模拟的运输边界。sanitizer 为 ASan+UBSan；受 ptrace 环境限制，
LeakSanitizer 单独记未运行。

扩展客体入口为 `tests/glibc_static_guest.py --suite files-extra`。它绑定当前
source、完整 glibc SDK、程序 ELF 和实际系统镜像；公共 fixture 覆盖目录身份、
UTF-8/长名字、多页 cookie、scandir、CLOEXEC、配额回收和多线程定位 I/O。
native 父进程 fork 后 exec glibc 子进程，双方真实并发使用同一文件描述，父进程
顺序读取必须保持字节串和最终 offset；另验证子进程目录 stream 在父进程 rename、
删除和同名重建后保持身份。父进程使用现有 native libc，仅 glibc 接收端属于本模块。

真实客体 fixture `files_public_probe.c` 链接完整候选 glibc，支持默认三 worker
并发、`single`、`service-death` 和 `inherit`。`files_exec_parent.c` 用现有 newlib
SDK 编译，真实 exec 到带 `XOS_GLIBC_G3_EXEC_RECEIVER` 标记的 glibc 子镜像，
验证共享 offset、FD 31、CLOEXEC 过滤及全部 16 个远端 handle 的可重用性。

服务死亡使用独立镜像：`scripts/build.py --glibc-files-death-probe --output-dir
build/glibc_files_death_system`。该选项要求独立 build 子目录，写入顶层 manifest 的
`glibc_files_death_probe: true` 和构建摘要；默认构建记录 false。仅 files 服务的
翻译单元启用测试宏，精确的只读 open 请求 `/.glibc_g3_service_death` 触发服务
自行 exit(86)。公开 probe 在 READY 后发出该请求，验证被中断 RPC
及旧描述后续均为 EIO。正常镜像不含此触发代码，也不改变受保护服务的 kill 策略。
服务没有 console route，harness 依据已观察服务 PID 的内核回收 trace、进程表和
资源变化确认真实退出。

## 路径变更

glibc `mkdir` 使用现有 files op 15。FAT 后端使用当前安装盘的目录授权，
`mode_t` 不写入持久 POSIX mode。`rename` 使用现有 op 16，旧路径通过
`name/name_length` 传输，新路径通过 `data/length` 传输。两条路径均按调用进程
的当前工作目录解析，同一次服务调用内完成现有名称替换。

`rmdir` 使用 files wire v2 op 32，通过 `name/name_length` 传输路径，其他
请求控制字段为零。成功响应的元数据和负载长度均为零。files 在同一次服务请求
内验证授权、目标类型和空目录条件，再执行删除。常规文件返回 `ENOTDIR`，非空
目录返回 `ENOTEMPTY`。该调用受与 op 13 相同的维护限制。旧 op 13 继续允许
原有客户端使用 `allow_directory`。旧服务会拒绝 op 32，glibc 直接返回错误并
保留工作盘状态。
