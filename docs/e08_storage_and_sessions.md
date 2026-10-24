# E08-1：存储、文件会话与流式装载

状态：受限实现完成，74 组验证通过，最终结论见 state.md 和 work_log/0012_e08_1_storage.md。
本阶段不移植 binutils/GCC，不接入 POSIX 文件描述符；后者属于 E08-2。

## 阶段设计判断

E08-0/pre1 → 存储/文件 ABI → 进程/libc → binutils → C → C++ → 集成的依赖合理。
分开执行编译器、在系统内构建编译器、系统重建，能给每步真实可检验的停点。

落实时校正三处表述：

- 宿主 Mach-O 的体积只能辅助容量估算，不能证明 XOS Seed 的大小或峰值内存；
  512 MiB RAM/2 GiB 盘是本次实施基线，仍须用将来的 Seed 实测复核。
- 异常、RTTI、TLS 是项目选择的 E08-5 兼容目标，不是任意 G++ 可执行文件的
  必然前置。保留现有目标，不在 E08-1 实现或降低这个 gate。
- 吞吐不足应先量清块传输、IPC、拷贝及读取模式；按需分页不是自动的性能解法。
  当前选择流式读取并预载用户页，保持失败回滚。

pre1 是设计完成，E08-1 gate 是实现后的验收，不把它写成“实现前先通过实现 gate”。

## 资源与启动

QEMU 默认 512 MiB RAM；物理页管理上限 512 MiB；每进程最多 65536 个 4 KiB
用户页（256 MiB，包含栈），虚拟用户窗口仍为 1 GiB，8 个任务、16 个完成记录。
页分配使用扫描提示避免反复从第一页遍历；usable 区间只纳入完整的 4 KiB 页。
现有低地址 direct map 能在同一 PD 中覆盖这个物理窗口，不需更换启动协议。

`make disk` 对新路径默认创建稀疏 2 GiB FAT32 卷，512 MiB 作为测试候选。
已有盘保持原样，包含原 16 MiB FAT16 工作盘；不自动升级、扩容或格式化。
可显式 `python3 scripts/make_work_disk.py work_disk_2g.img --size-mib 2048`，
再以 `python3 scripts/run_qemu.py --work-disk work_disk_2g.img` 启动。
新卷仍是无分区表的单卷；ATA LBA28/每次最多 8 扇区机制不变。

## 可信会话与资源归属

`sys_file_session`（27）仅对 files 服务开放，接收任务槽索引和用户态输出指针，
返回 `file_session_info {pid, request_handle, response_handle}`。只报告已经提交、
仍存活的客户端。普通子程序通过原 `ipc_handles` 获得自己的请求/响应端点。
构造/块设备权限不随之继承。

内核绑定发送者/接收者的真实 PID，files 按 8 个槽轮询各自邮箱。
端点池 19 项；token 在一次启动中单调分配且不复用，耗尽拒绝，避免迟到回复
因槽位复用落到新客户端。退出/abort 回收两端队列，发送到死接收者返回错误。
files 根据内核返回的 PID 变化关闭旧会话的文件，并清除其未提交临时文件。
请求中的 reserved/自报 PID 不承担鉴权。

每会话最多 16 个打开实例；FatFs 全局对象锁表 32 项（0020调整），耗尽返回真实错误。
文件句柄在槽内单调分配，旧句柄不能复用；每个打开实例独立游标。
files 是当前不可通过 kill 终止的 bootstrap 服务；服务自身故障仍是真失败，
没有自动重启。服务不存活时不构造连接到死服务的新子进程。

## 文件 ABI v2

消息仍为 4096 字节，路径字段扩为 256 字节，数据区相应缩小；内核/服务/SDK
必须一起重建。绝对路径和不带前导 `/` 的路径都从卷根开始，无 cwd、`.`、`..`。
支持目录和 ASCII 长文件名，保持 FAT 不区分大小写语义；拒绝非 ASCII、控制字符、
冒号、反斜线、重复分隔符、尾部点/空格及内部恢复文件名，不静默截断。

FatFs 使用静态 LFN 工作区（单一 files 执行上下文），ASCII 转换器明确不提供
完整 Unicode。对象锁用于拦截通过大小写或短名别名绕过的写打开/删除/改名冲突。
接口支持 open/read/write/seek/close/stat、目录分页、mkdir、rename、remove、sync；
尚无 POSIX open/create 标志。创建文件走 replace 协议。

不再有 4 文件/24 KiB 上限。大小/偏移是 u32，保守上界 0xfffffffe，同时受介质
剩余空间和 FAT 格式限制。写返回实际字节；seek 返回实际位置。
list 采用二进制长度前缀记录，名字含空格时不会被分词破坏；cursor 是目录枚举位置，
目录并发修改时不承诺稳定快照。文件版本字段暂为 0，装载一致性依靠持有读锁。

保存为 begin → 连续 offset 的 chunk → commit/abort。内容直接流入磁盘临时文件，
不使用与文件等大的 RAM staging。当前全局允许一笔保存；其他活会话收到 busy，
不能抢占正在保存的内容。空间检查包含按簇取整与元数据余量，仍处理实际短写。
提交延续 temp/journal/backup/target 顺序，journal 记录完整目标路径。
打开期间拒绝替换；正常同步/重启是本轮保证，任意掉电事务原子性未证明。

`block_bench` 是最多 8 MiB 的只读诊断操作，仅统计完成字节，不向客户端暴露
原始扇区内容；用于固定配置测量，不是通用原始磁盘 API。

## ELF 与终端

`elf::inspect_reader` 只读取 ELF header 和有界 PHDR；所有既有范围、对齐、W^X、
入口和页上限校验保留。`spawn_file` 打开文件，保持读锁，按段/页精确读取到
4 KiB scratch，零填 BSS；关闭源文件成功后才提交子任务。失败关闭并 abort。
大缓冲是静态服务工作区，不占小内核栈，也不按文件大小分配 supervisor 缓冲。
只读启动模块仍有 128 KiB 限制；这不再是工作盘 ELF 的上限。

`exec-file` 等待结果，`spawn-file` 返回 PID；后者用现有 kill/wait 回收。
`ls [path]` 分页列出目录，`mkdir`/`mv` 提供对应最小操作，cat 分块输出。
编辑器仍为 8 KiB 缓冲、命令按空格解析，尚不支持带空格路径的终端引用语法；
SDK 本身可访问含空格的名字。argv 的 8 项/63 字节限制留待 E08-2 扩展。

## 宿主安装与备份

关闭占用该盘的 QEMU 后显式运行：

```sh
python3 scripts/work_disk.py work_disk_2g.img mkdir /bin
python3 scripts/work_disk.py work_disk_2g.img import /bin/example.elf build/user_hello.image.elf
python3 scripts/work_disk.py work_disk_2g.img export /bin/example.elf exported_example.elf
```

目录需先建立；import 拒绝覆盖目标，export 拒绝覆盖宿主输出。工具只接受常规镜像
文件，并用文件锁避免并发访问；仍要求离线操作。它把宿主输入转存到 FAT，运行时
XOS 仍自己经 ATA/FatFs 读写，不启动宿主代执行服务。
宿主桥复用本仓库 FatFs；导出比较是客体外的读取交叉检查，不等于独立 FS 实现验证。

## 验证边界

真实 gate 在 tests/e08_storage_smoke.py：512 MiB/2 GiB FAT32；>128 KiB 静态 ELF；
BSS/私有内存；子程序路径访问、目录/改名/空格名字；流式 256 KiB 保存和字节比较；
双启动；并发 RPC/保存冲突；取消与会话复用；65536 页分配上限与全部页表回收。
另保留 FAT16 旧盘、物理满盘保存失败、ELF ASan/UBSan 与 AArch64 编译检查。
吞吐为固定 QEMU/TCG、主机缓存下有限样本，不是真机/长期/冷缓存性能结论。

尚无：POSIX 文件/libc 适配、cwd/环境/pipe/一般 spawn、动态堆、工具链 Seed、
Unicode、sysroot 只读授权、服务重启、UEFI、SMP 或任意掉电一致性证明。
