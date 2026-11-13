# 文件身份、目录引用、延迟删除与真实近满盘回归

2026-11-12。分支 `codex/posix-identity-20261112`，实现基线
`158a9b99550c03b97e74e3b9e4c2fd6a288c8bf3`。本记录对应用户授权继续实施的
FS-01/02/04/08，包含 FS-03 的真实介质宿主回归与客体测试代码；服务端路径解析也
移除了 FS-05 所述的 libc 中间分量逐次 stat RPC。共享状态、债务总表和总报告由
主线合并者汇总，本分支不改写它们或既有冻结证据。

## 实现与选择

`files.cpp` 将打开描述和文件对象分开：独立 open 的偏移/标志独立，dup/fork 共享
描述，同一 inode 的所有描述共享一个 FIL。保留 FatFs 锁，不通过关闭 `FF_FS_LOCK`
制造表面兼容。目录对象持有父对象及实际名字；cwd、目录流、文件对象及 staging
引用这条关系。因此目录 rename、旧名重建、打开后 unlink 和 rename 替换都不会
把已有引用指向另一个 inode。

仍被引用的已删除/被替换对象保留在服务专用隐藏名字空间，最后引用才关闭并回收。
失败 close/unlink 留在对象表重试，并阻止 maintenance 把它们误认成已经清理完毕。
服务启动先恢复 journal，再清理无进程引用的隐藏残留。普通文件与空目录替换保留
原 journal/backup 路径和 recovery gate；staging 父目录已移除时不向重建的旧名提交。

FatFs 只新增约 47 行的 `f_rename_open` 窄接口：要求源对象的 sole FIL/锁匹配，
同步后移动目录项，并重新绑定 FIL 与锁键。原 `f_rename` 的打开对象拒绝保持。
`ff.c`/`ff.h` 原始许可声明保留，本地改动在第三方 README 与组件清单登记，实际
sha256 已更新。没有改动自动生成文件、工具链锁或 FatFs 配置。

libc 将 cwd 交由服务持有，增加 `fchdir`、目录 FD 和 `dirfd`；路径遍历在服务的一次
请求内完成。loader 在子进程启动前委派 cwd，fork 同事务克隆，exec 的 CRT 仅初始化
尚未初始化的会话。loader/read_all 使用显式只读 pin，与同 inode 的可写打开互斥；
普通只读 open 不再借用 FatFs 的全文件写冲突。原子替换换名字而不改旧 inode，因而
允许旧 reader/pin 继续读旧内容。

新增 files op 26 `cwd_set`、27 `cwd_get`、28 `resolve_path`，保持 v2 wire 布局。
open bits 10/11 为目录/pin，stat bit1 为 unlinked；新增四个明确类型/长度错误。
共享头、SDK、e04 速查及其检查器已同步；合并者把同一条目写入共享 ABI registry。
详细限制与进程授权语义见 [文件身份契约](../contracts/file_identity.md)。

内置 filetest 与 e08_probe 不再断言“普通读者存在就不能替换”，改为实际验证替换
成功后旧 reader 仍读旧字节、新路径读新字节；独立读写打开和合法 `..` 路径也验证
真实结果。没有只把 `busy` 预期改成零而删掉内容检查。

## 实际验证

宿主为 Linux x86-64；`c++ (Debian 14.2.0-19) 14.2.0`、Python 3.12.14。
所有介质是 `make_work_disk.make_image()` 生成的私有 16 MiB FAT16 内存/临时镜像，
没有挂载或写入宿主真实分区。

| 检查 | 实际结果 | 范围 |
|---|---:|---|
| `python3 tests/file_identity_host.py` | 25 + 23 + 9 组通过 | 原语义、文件/目录身份、真实 libc→SDK→files→FatFs；仅 kernel IPC/会话查询为宿主边界 |
| `python3 tests/file_recovery_faults.py` | 21 组通过 | 原 staging/journal/backup 故障矩阵 |
| `python3 tests/libc_startup_host.py` | 15 + 6 组通过 | CRT/启动输入及 execvp PATH 边界 |
| ASan + UBSan 的真实文件服务身份程序 | 25 + 23 组通过 | 未报告内存/未定义行为错误；关闭 LeakSanitizer，原因见下文 |
| 7 个改动运行时 TU 的仓库 flags 编译 | 7 个通过 | files、file_client、newlib_syscalls、load、command、file_ui、e08_probe；宿主编译器，不是锁定交叉工具链 |
| 新 guest probe 的 newlib 头语法编译 | 通过 | 仅编译，不运行 |
| Python 语法与 guest runner `--help` | 通过 | file_identity_host/guest、file_smoke |
| 真实 FatFs 近满盘准备器 | 通过 | 精确仅剩 1 簇，重复输出排他拒绝，原输出字节保持 |
| `python3 tests/abi_doc_consistency.py` | 通过 | 当前文件 op 20–28 与既有 syscall 表 |
| FatFs 组件 sha256 核对 | 3 项通过 | ff.c、ff.h、原许可文本；不是全 SDK license-audit |

前三项合计 99 个测试组，其中新增身份/全链路组为 23 + 9。ASan 重复执行的组不再
加入这个总数。LeakSanitizer 在该宿主的 ptrace 环境下报告运行器不支持，故使用
`ASAN_OPTIONS=detect_leaks=0` 执行 ASan/UBSan；不能把它记为泄漏扫描通过。
对象表/描述表的全部引用回收另有真实服务断言。

23 组身份测试覆盖：独立偏移、共享缓存/append/truncate、LFN/SFN 同一对象、打开
rename/unlink、同名重建、打开目标替换、跨父目录替换、活 cwd 和已删除父链、只读
pin、clone_session、原子保存新旧 inode、staging 父目录 rename/remove、真实近满
回滚、真正满盘短写、错误 FIL 拒绝、失败延迟删除重试、目录 journal 恢复、启动
残留清理、SFN 祖先防护、维护阶段遗留关闭所有权。

可重跑命令：

```sh
python3 tests/file_identity_host.py
python3 tests/file_recovery_faults.py
python3 tests/libc_startup_host.py
python3 tests/abi_doc_consistency.py
python3 -m py_compile tests/file_identity_host.py tests/file_identity_guest.py tests/file_smoke.py
c++ -std=c++20 -ffreestanding -fno-builtin -w -Isrc/user/include -Isrc/shared/include -Isrc/third_party/newlib/x86_64-elf/include -fsyntax-only tests/fixtures/file_semantics/file_identity_guest.cpp
```

`build/file_identity/report.json` 保留实际编译命令、运行输出和源输入哈希；
`runtime_compile.json` 保留七个 TU 的完整 flags、退出码和诊断；
`target_build.json` 保留系统构建阻断；`final_validation.json` 汇总本组结果及原始
日志路径。它们是可重建工作产物，关键通过/未运行信息已写在本记录中。

## 客体代码与未运行项

`file_identity_guest.cpp` 只调用公开 libc/SDK，包含独立打开/旧 FD 内容、cwd 目录
rename/recreation、目录流/fchdir、目录替换、pipe 同步的 fork、spawn 和同 PID exec。
近满模式使用准备器产生的真实近满介质，验证 ftruncate/洞写回滚、零剩余簇短写、
rename journal 空间失败保留源/目标，以及释放空间后原子保存恢复。

`file_identity_guest.py` 检查系统 manifest 的源码和 ISO 哈希，构建探针，在 Guest
启动前准备各自独立的工作盘，运行 xsh 与可选的显式 dash 入口并检查进程资源回收。
不会按 mtime 自动挑选 dash；不提供 dash 时明确登记未运行第二入口。

实际尝试：

```sh
python3 scripts/build.py --output-dir build/identity_system
```

前置检查返回 `NASM not found; install it or set NASM=/path/to/nasm`，因此完整目标
构建、SDK 包、guest 的身份/fork/exec/双 Shell/近满盘、xsh 内置 filetest 和 E08
客体回归均 **未运行**。没有声称 NASM 缺失证明其他环境或全部工具链都不可用。
全 SDK license-audit 同样未执行，因为没有本次构建生成的 SDK 清单。

合并后先按当前锁定工具链生成组合 SDK/系统，再执行：

```sh
python3 tests/file_identity_guest.py --system build/identity_system
python3 tests/file_identity_guest.py --system build/identity_system --dash-elf build/dash/dash.elf
```

第二条明确替换为本次 SDK 重建的 dash 路径。不能拿历史静态 libc/旧 SDK 的产物
宣称 cwd 新语义已验收。

## 保留限制

`st_ino` 是服务生命期内的 16 位身份，不是持久磁盘元数据；对象 256、描述 32、
会话 8、每会话句柄 16 和路径 255 字节的预算仍存在。文件权限/UID/GID/时间戳仍
没有完整 POSIX 元数据层；没有 hard link/symlink、跨卷 rename、POSIX 文件锁或
files 崩溃后恢复活 FD。延迟删除需要空闲目录项，元数据耗尽可能失败。FatFs 的
任意扇区断电行为不在本组保证内，原 recovery gate 仍保留。

FS-01/02/04/08 的源码行为已实现并有宿主证据；新客体验收资格和 FS-03 的客体
退出条件仍待上述命令实际执行，不将这两种状态混为“已验收”。


## 装载链补验：继承 cwd 编码与错误域

后续 SL4 真实 libc+loader 用例发现本组遗漏：libc 用 `working_directory=nullptr`
表示保留服务 cwd 引用，但 loader 的 startup 编码仍无条件复制字符串，导致 spawn
和 exec 在 prepare 阶段失败。现改为仅编码显式路径；空指针保持 extension 的零值，
由已委派/同 PID 的服务 cwd 提供身份。测试用实际 ELF 解析和启动编码走到 kernel
create/exec_prepare，再在 kernel 边界返回受控失败，因而不会把“仅检查输入文本”
冒充验证这条装载链。

同一组补验复现旧 `posix_spawn` 将数值相同的 kernel/file 状态混淆：kernel denied
被报 ENOENT，resources 被报 EBUSY，process busy 被报 EISDIR，file would_block
被报 E2BIG。现在普通 spawn 和 exec 共用阶段化 errno 映射，并为 cwd/句柄转交、
读取映像和关闭文件失败附加 `launch_stage::file_setup`；它是 SDK 诊断枚举增量，
不是新增 syscall 或文件 op。supervisor 同步显示该阶段。process busy 在这个进程
上下文映射 EBUSY，不借用线程 address 的同值 EFAULT。

`python3 tests/libc_startup_host.py` 现为 15 启动 + 6 execvp + 10 spawn 错误域 +
1 exec 继承 cwd 组全部通过。10 组还核对失败不改输出 PID、文件打开/关闭平衡、
已创建但 cwd 交接失败的子进程恰好 abort 一次。原 99 组之外新增 11 组，客体仍
未运行。旧失败、新通过日志见 `build/native_dev/runtime/`；补验后重新运行的文件
身份宿主结果仍为 25 + 23 + 9 组通过。
