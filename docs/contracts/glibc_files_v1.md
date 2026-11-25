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
files wire 与内核 ABI 均保持现状。编译断言位于 `files_public_layout.c`。

FAT 的权限和时间投影遵循文件元数据契约：创建 mode 由服务的固定权限规则
解释；uid/gid 为 0，nlink 在延迟删除时为 0；mtime 同步投影到三个时间字段。
旧服务的空 metadata trailer 可接受，已提供的 FMET v1 trailer 必须严格有效。
当前 identity 是服务定义的 16 位命名空间：根 1、FAT 2–65533、`/dev` 65534、
`/dev/null` 65535。零 identity 和超界值作为协议错误处理。

## FD、并发与服务会话

每进程有 32 个 FD 和 32 个本地 open-description 记录。普通文件句柄的实际
并发上限由 files 服务的 16 handle 配额决定。`dup` 与 `dup2` 引用同一个记录，
因此共享服务侧 offset；CLOEXEC 则属于各个 FD。独立 `open` 保持独立 offset。

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

## 协议校验与服务死亡

IPC endpoint 来自当前进程的 `sys_file_endpoints`。每次操作使用单调时钟的
5 秒绝对截止时间，空队列期间最多睡眠 1 毫秒后重新接收。现有 files endpoint
属于旧 IPC 通道，当前没有适用的带截止时间接收原语。

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

工作目录仍由 loader/files 服务维护的 identity 继承。本模块实现接收端恢复；
glibc 的 fork/exec/spawn 出站路径须由后续独立模块提供。
`.xos.exec` opt-in 只由专门的 G3 验收 fixture 声明，CRT 不全局添加该标记。

## 明确支持范围

`F_GETFD/F_SETFD/F_DUPFD/F_DUPFD_CLOEXEC/F_GETFL` 支持；`F_SETFL` 可变更
本地 O_NONBLOCK；终端对象请求该标志返回 ENOTSUP 并保持原 flags。改变
O_APPEND 返回 ENOTSUP（既有服务没有该句柄操作）。
文件系统无 symlink，NOFOLLOW 和 AT_SYMLINK_NOFOLLOW 按此 profile 处理。
相对路径的 `openat/fstatat` 支持 AT_FDCWD；其他 dirfd 相对路径返回 ENOTSUP。
`AT_EMPTY_PATH` 可查询已打开的 FD。未知操作返回确定错误。

路径型启动重定向、目录枚举、文件锁、pread/pwrite、mmap 文件
映射、glibc 出站 fork/exec/spawn 与异步取消暂不属于本模块。fsync 调用真实 files
sync，其他尚未实现操作沿用上游或 XOS 的明确失败路径。

## 验证入口

```sh
python3 tests/glibc_g3_files_host.py --output build/glibc_g3_files_host
python3 tests/glibc_g3_files_host.py --sanitize --output build/glibc_g3_files_sanitize
```

宿主回归替换内核陷阱而保留生产 FD/IPC 状态机，覆盖故障注入、并发、继承、
管道 lease 和原子写；另一组链接实际 `files.cpp`/FatFs，验证真实文件服务。
这两类报告分别标明模拟的运输边界。sanitizer 为 ASan+UBSan；受 ptrace 环境限制，
LeakSanitizer 单独记未运行。

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
