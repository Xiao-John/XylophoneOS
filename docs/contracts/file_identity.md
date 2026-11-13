# 文件与目录身份、独立打开和 cwd 引用

2026-11-12。状态：`implemented_unverified`。真实 libc/SDK/files/FatFs 宿主回归已
执行；新客体探针与近满 FAT16 镜像准备器已实现，尚未执行客体验收。本契约仅定义
本节列出的有界子集，不声明完整 POSIX 或持久 inode 编号。

## 身份与所有权

files 服务继续串行处理请求。每个正在使用的普通文件只持有一个 FatFs `FIL`，
每次独立 `open` 创建自己的打开描述：偏移、访问方向、`O_APPEND` 等属于该描述。
`dup`、文件句柄转交和单线程 `fork` 引用原描述，因而共享偏移。独立描述引用同一个
文件对象，读写与截断看到同一份 FatFs 缓冲区和当前长度，不再通过多个 `FIL` 互相
覆盖目录项。`FF_FS_LOCK=32` 保留，普通 FatFs API 的锁拒绝行为也保留。

对象由已经解析的 FAT 目录项 sector/offset 识别，LFN、SFN 和 ASCII 大小写别名
归于同一对象。`stat`/`fstat` 的 `st_dev` 沿用单卷值，`st_ino` 在本次服务生命期
<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:8574e7e2c3de7e449fc4346d5ad041ba2f0c67700679e316e0631e0ccf272cae -->

内非零且不复用：根目录为 1，FAT 对象编号从 2 到 65533 单调分配；
65534、65535 分别保留给虚拟 `/dev`、`/dev/null`，不随对象槽释放改变。
重命名移动目录项位置，同时迁移

<!-- /coderabbit-ai-generated:v1 -->
身份映射。删除后同名创建取得新编号；原打开描述仍指向旧对象。编号不写入磁盘，
重启后的 inode 数值不承诺与先前相同。

目录对象保留父目录对象及实际存储的叶子名，不保存会失效的完整绝对路径。文件对象、
子目录对象、cwd、目录句柄和原子保存 staging 都拥有相应目录引用。重命名只更新被
移动对象的父目录和名字，其子孙的路径随引用链变化。SFN 访问取得目录的实际 LFN，
因此 `getcwd` 不依赖调用方使用的别名拼写。

关闭描述或会话退出释放引用。最后一个文件对象引用先同步并关闭 `FIL`，再完成
延迟删除。关闭或删除失败的零引用对象仍保留在表中，服务循环继续重试，不把尚持有
FatFs 锁或磁盘簇的槽当作空槽。maintenance acquire/release 同时检查这类待清理
对象，不能在其存在时宣布文件写入已经静止。

## 打开、读写和目录流

- 普通文件允许多个独立只读、只写或读写打开。每个 `O_APPEND` 写请求在服务内
  以该共享对象的当前 EOF 为起点；独立描述的普通偏移互不改变。
- `O_TRUNC` 和 `ftruncate` 作用于共享对象长度，不修改其他描述的偏移。
  越过 EOF 的 `lseek` 不分配空间；随后写入显式零填充间隙。零填充或扩展失败
  尝试回滚原长度，回滚失败继续采用原有 recovery gate。
- 底层已完成部分写入时返回实际字节数；完全未写入且无空间时返回 `ENOSPC`。
  本次真实满盘回归验证了只剩一簇时的失败回滚，以及无剩余簇时的两字节短写。
- `open(path, O_RDONLY | O_DIRECTORY)` 创建目录描述；普通文件打开仍拒绝目录。
  目录描述可用于 `fstat`、`fchdir`、`dup`、继承和 SDK list，不能用于字节读写、
  seek 或 truncate。`opendir` 以 `O_CLOEXEC` 打开目录 FD，`dirfd` 返回这个 FD，
  `closedir` 关闭它。`readdir` 继续使用有界分页，不承诺修改中的目录快照。

## rename、unlink 与原子替换

对仍有引用的文件执行 unlink，会把该 inode 移到服务保留的根目录隐藏名字，立即
移除原来的公共名字。后续旧 FD 读写仍作用于旧 inode；`fstat` 返回 `st_nlink=0`。
最后一个引用释放才真正回收簇。重新创建原名字不会重新连接到旧对象。

rename 保持源对象身份，包括打开的普通文件和目录。普通文件可以替换普通文件；
目录可以替换空目录，也可以跨父目录移动。非空目标目录返回 `ENOTEMPTY`；文件与
目录互换返回 `EISDIR`/`ENOTDIR`。祖先判定使用真实目录项身份，SFN/LFN 别名不能
使目录进入自己的后代。

已存在目标仍有引用时，替换先把目标保存在 journal 指定的备份位置，安装源对象，
再把旧目标转为独立的延迟删除对象。旧目标的 FD/cwd/目录流不会指向新对象。
未被引用的旧目标在事务清理时删除。

单文件原子保存仍采用 staging + journal + backup；begin 的空间预算、提交完整性
检查、故障恢复和 recovery gate 没有改为直接截断。保存创建新 inode，因此旧 FD
读旧内容，新打开读提交后的内容。staging 保留目标父目录引用：父目录 rename 后，
提交发生在移动后的目录；父目录被移除后，提交失败，不能落到旧名字下重新创建的
另一个目录。成功提交后清理临时元数据；恢复失败禁止继续服务读写。

服务启动先处理原有 journal，再清理保留名字空间中的延迟删除残留。进程已经不再
存在时没有需要恢复的 FD 引用；残留文件或空目录可回收。清理失败进入 recovery
gate。该处理不扩大底层 FAT 的掉电保证，任意扇区写入中断不是本次已验收范围。

FatFs 的本地 `f_rename_open` 扩展仅接受该服务独占的单个普通文件 `FIL`，校验其
锁与源目录项一致，同步后执行原重命名逻辑，并把 FIL/锁表绑定到新目录项。普通
`f_rename` 仍拒绝打开的文件；错误 `FIL` 不能借此迁移其他对象。源目录项删除成功
后新目录项已经生效，最终同步失败不会伪称恢复到旧路径；服务据此进入恢复限制。
本地改动与上游许可见 [FatFs 说明](../../src/third_party/fatfs/README.md)。

## cwd、路径与进程生命周期

相对路径在服务内从当前会话的目录对象开始逐分量解析。中间分量必须已经存在且是
目录，`missing/../file` 和 `file/../other` 不会被词法化简为成功。`.` 保持当前
目录，`..` 使用父目录引用，根的父目录仍为根。路径字节/UTF-8/名称限制在协议入口
处理；libc 不再对每个中间分量单独发送 `stat` 请求。

`chdir` 更新会话目录引用；`fchdir` 使用调用者拥有的目录句柄。父目录 rename 后，
`getcwd` 和相对打开沿新路径；旧名字重新创建不改变已有 cwd。空 cwd 被 rmdir 或
被 rename 替换后，cwd 对象仍保留，但不再有公共绝对名字：`getcwd` 返回 `ENOENT`，
从中创建/访问命名子项返回 `ENOENT`，`.`、`..` 及通过其他目录 FD/绝对路径离开仍
可用。目录引用使被删除的父链在需要时继续存活。

fork 的 `clone_session` 事务同时保留原 cwd 和打开描述；kernel ACK 失败回滚所有
新增引用。spawn 的装载器在启动新进程前委派目录引用：显式 working_directory
按父会话解析，否则继承父 cwd。子 PID 必须由内核会话信息证明属于调用父进程，
且尚未初始化 cwd；自报 PID 不构成授权。

同 PID exec 保留 files 会话。CRT 的初始化使用 initialize_only，已有 cwd 时不按
启动文本重开目录，因此 exec 前后的 rename/recreation 不会改变身份。旧静态 libc
中的文本 cwd 逻辑不会因服务升级自动改变；依赖这组行为的应用必须使用新 SDK 重建。

## 文件协议 v2 增量

4096 字节 request/response 布局、版本号 2 和 op 1–25 保持不变。新操作占 26–28。

| 操作 | 请求 | 成功结果 / 失败 |
|---|---|---|
| 26 `cwd_set` | `name` 为路径，或 `handle` 为调用者目录句柄；两者同时为空表示继承调用者 cwd。`offset=0/self` 修改自身，其他 PID 表示委派已认证子进程。`flags bit0=initialize_only` | 成功为 0；子会话未枚举返回 `would_block`，非子进程 `invalid`，已初始化子进程 `busy`；目录句柄类型不符 `not_directory` |
| 27 `cwd_get` | 无路径 | `response.name/name_length` 返回 NUL 结尾绝对路径，length 不含 NUL；已脱离公共名字空间返回 `not_found` |
| 28 `resolve_path` | `name` 路径 | 按当前 cwd 解析后返回绝对路径；中间目录必须存在，最终叶子可以不存在；不是未来打开的保留句柄 |

SDK 提供 `set_cwd`、`set_cwd_handle`、`get_cwd`、`resolve_path` 与目录句柄版本
`list`。`list` 请求的非零 handle 与 name 不能同时使用。

新增 open flags：bit 10 `open_directory`（只读且不能与创建/截断/append/pin 混合）；
bit 11 `open_pin`（只读普通文件，不能附带写选项）。stat/fstat flags 的 bit 1 为
`stat_unlinked`。新增状态：`not_directory=-10`、`is_directory=-11`、
`not_empty=-12`、`name_too_long=-13`，libc 分别映射到 `ENOTDIR`、`EISDIR`、
`ENOTEMPTY`、`ENAMETOOLONG`。

装载器、可执行预检及 `read_all` 使用显式只读 `open_pin`。已有可写描述时 pin
返回 `busy`，存在 pin 时新的可写打开同样失败；普通只读打开不锁住其他写者。
pin 保证的是已打开 inode 的内容在校验/装载期间不被写入；rename/unlink/原子替换
可以改变名字，pin 仍读原 inode。最终装载自己的 pin 才是保证，预检不代替它。
冲突沿原 load/open 错误通道返回，不能偷偷复制不一致内容后报告成功。

## 有界资源与未实现范围

沿用每会话 16 句柄、全局 8 会话和 32 打开描述；新增最多 256 个被引用的非根对象，
父目录引用也计入此预算。每次服务生命期最多发放 65534 个非根身份，不回绕复用。
身份或对象预算不足返回 `full`；已分配身份的对象仍能查询/重开。

路径与返回的绝对名字最多 255 个 UTF-8 字节（不含 NUL）；祖先链按这个有界路径
限制处理。FAT ASCII 大小写折叠、非法字符和保留服务名字空间沿用现行限制。没有
hard link、symlink、持久 UID/GID/mode/mtime 元数据或 POSIX 文件锁；`st_nlink=1/0`
仅表达当前有无公共名字，不能推出硬链接支持。延迟删除需要可用的保留目录项，
底层元数据空间耗尽时可以失败，不能承诺 unlink 一定不需要磁盘空间。

这些更改不实现 files 服务重启后恢复活 FD，不改变多线程 fork/exec 的既有限制，
也不把单个文件事务扩大成通用多文件事务。

## 验证与复跑

宿主 `python3 tests/file_identity_host.py` 编译实际 files/FatFs 与实际 libc/SDK，
执行原文件语义 25 组、新身份 23 组及 libc 全链路 9 组。仅 kernel IPC 传输/会话
信息使用测试边界；不复制业务实现。`tests/file_recovery_faults.py` 保留 21 组
原故障恢复回归；`tests/libc_startup_host.py` 保留 15 组启动和 6 组 execvp 边界。

客体入口：

```sh
python3 scripts/build.py --output-dir build/identity_system
python3 tests/file_identity_guest.py --system build/identity_system
python3 tests/file_identity_guest.py --system build/identity_system --dash-elf build/dash/dash.elf
```

最后一个路径必须指向使用这组 SDK 重建的明确 dash 产物，runner 不自动挑最新文件。
runner 校验系统 manifest 与源码/ISO 字节，离线复制私有盘后再启动 Guest。近满镜像
通过真实 FatFs 写满到仅剩一簇，输出采用排他创建，不覆盖既有镜像。客体覆盖身份、
cwd、目录流、fork、spawn/exec、近满/满盘及退出后的进程资源回收；可选 dash
运行同一探针。当前环境实际构建被缺少 NASM 阻断，所以这些客体检查仍为 `not_run`。
