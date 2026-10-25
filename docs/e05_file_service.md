# E05：RAM 文件服务、编辑器与文件装载

实施于 0008。E05 当时使用 RAM 后端；E07 已把存储替换为独立 FAT16 工作盘
（ATA PIO + FatFs），客户端协议、打开实例和编辑器接口保留。持久化/同步/
恢复边界见 `e07_persistent_work_disk.md`。源码、SDK 与证据见
`history/e01_e07.md`、`history/e01_e07.md`
和 `src/shared/include/xos/file_abi.hpp`。

## 角色与拓扑

| 组件 | 职责 |
|---|---|
| `files`（ring3 任务） | 平铺 RAM 文件表、打开实例、块读写与原子替换 |
| supervisor（ring3 任务） | 终端、编辑器、文件客户端、ELF 装载策略 |
| 内核 | 端点容量、带持有者检查的消息复制、任务启动；不解析路径/文件/ELF |
| SDK | `file_client` 请求/响应、短读短写、版本检查、装载缓冲 |

`files` 和 supervisor 一样由内核按宿主生成的可信段清单装入；内核只负责映射/
启动，不解析 ELF。supervisor 与 files 使用两个固定端点：请求（supervisor→files）
与响应（files→supervisor），单条消息 4096 字节。端点容量按端点记录，E03 的旧
端点仍为 64 字节，不改变其回归语义。

## 文件与打开实例

- 文件：名字（最多 15 个可打印 ASCII，不含 `/`、`\`）、大小、版本、内容槽。
- 打开实例：文件索引、游标、读写方向；每个实例独立，两个打开同一文件不会
  共享偏移。
- 上限：4 个文件、每文件 24 KiB、8 个同时打开；总数固定，无目录/层级。
- 读：从游标返回最多请求长度，短读合法；游标到文件尾返回 0（EOF）。
- 写：从游标写，返回实际写入字节；到文件容量时短写，不越界。
- seek：设置绝对游标，允许写到当前大小之后；不提供相对 seek 或截断 op。
- 错误：`not_found`、`invalid`、`full`、`no_space`、`busy`、`bad_handle`、
  `io`、`would_block`；客户端不把错误映射成成功。
- 打开期间文件替换返回 `busy`；删除有打开实例的文件也返回 `busy`。

## 原子替换与失败一半

编辑器和装载器都不直接截断旧文件。替换流程：

1. `replace_begin(name, total)`：检查名字、容量和 staging 是否空闲；记录
   `(name,total,owner_pid)`，不修改旧文件。
2. `replace_chunk(offset,data)`：按顺序写入 staging；offset 必须等于已写长度，
   超出总量/消息上限返回 invalid。
3. `replace_commit`：再次检查容量、打开实例和 staging 完整性，然后把 staging
   复制到正式槽并递增版本。
4. `replace_abort`：丢弃 staging；失败路径总是 abort，旧文件保持不变。

staging 带 `owner_pid`：同一客户端重复 begin 返回 busy；不同 PID（例如 supervisor
重启）会在新 begin 时丢弃旧 staging。它不是安全凭证，只是单客户端服务的残留
清理；没有 sender 身份的内核证明。客户端在超时/发送失败时返回错误，不自动重放
写操作；commit 是唯一提交点，不会把分块重试变成重复写入。

## 编辑器

`edit <file>` 进入 raw line 模式，正文行不经过命令分词器：

- 普通行原样追加，包括空行、连续空格和行尾空格；行结束写一个 `\n`。
- 只有以 `:` 开头的行是命令：`:w`、`:wq`、`:q`、`:q!`、`:p`、`:c`、`:help`。
- 保存调用原子替换；失败时打印错误并保留编辑缓冲区，旧文件未被截断。
- 缓冲区上限 8 KiB；行上限 159 字节，超长行拒绝并保留缓冲区。
- `:q` 在 dirty 时拒绝；`:q!` 丢弃；`:wq` 仅在保存成功后退出。
- 限制：正文不能以 `:` 开头（目前没有转义）；不是全屏编辑器，没有撤销/搜索。

## 装载器改接文件

- `exec-file <file>`：文件服务 `read_all` 先把整个文件读入有界缓冲区，检查
  `stat` 与 `open` 的版本一致，并保留打开实例直到读完；期间替换会被拒绝。
- 读完关闭后再调用 `spawn_buffer(name, bytes, size, ...)`；ELF 检查、段映射和
  启动都使用同一份内存快照，绝不第二次读取文件。
- 普通 `exec <image>` 仍读取只读启动模块，但同样先复制进缓冲区再检查/映射。
- 当前文件上限 24 KiB，低于 SDK 的 64 KiB ELF 上限；超出返回 `no_space`。

## E07 接缝

协议只暴露名字、offset、length、version、状态和字节，不携带 RAM 指针、槽索引
或运行时句柄。文件服务的 `slots`/`staging` 是内部实现；E07 可以把后端换成
块设备上的持久文件系统，保留 `file_abi.hpp` 的客户端语义和 supervisor 命令。
当前固定槽不会自动回收成更大的连续空间；删除只释放该名字，不压缩存储。

## 验证与边界

`make smoke` 的 E05 8 项覆盖：文件服务启动/列表、短读/EOF/独立打开/容量保留/
无效句柄、编辑器空行与连续空格、修改既有文件、缺失文件错误、删除、文件装载
执行。旧 49 项回归保持通过。

未实现/不声称：重启持久化、目录、权限 ACL、多客户端并发、阻塞文件锁、服务重启、
崩溃恢复、POSIX errno/open flags、文件时间戳、配额、原生编译、完整 libc。
E07 已加入同步/恢复和有限掉电边界；E06 已选择 newlib 并接入 SDK。当前服务绑定
supervisor 单客户端。
