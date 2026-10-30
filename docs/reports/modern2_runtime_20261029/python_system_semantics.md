# Python / LocalPilot：下一项系统语义的最小边界

2026-10-29。仅设计与实际源码调用点核对；不分配ABI，不声明select、subprocess、文件安全或Agent Core可用。
固定私有只读来源为LocalPilot main `9a21ebbe6621de43be6568b64433230c317eb81a`。
[源码回执](source_audit.json)只记录路径、SHA256、import/调用名称与行号，不包含私有源正文。
原始Agent Runtime、macOS安装及源码安全检查均保持原样。

## 原始依赖链为什么停在这里

pypdf 6.1.1的包入口依次导入文档/页面相关模块，`_page.py:67`接入filters，
`filters.py:42`无条件导入subprocess；该导入不是实际运行PDF外部工具的证据。
CPython 3.14.9的`Lib/subprocess.py:58`把fcntl当可选模块，但`:106`必须导入
`_posixsubprocess.fork_exec`，`:124–125`再导入select/selectors。
当前首个异常会遮住后续缺口。不能删除filters的原始import或伪造_posixsubprocess
让“普通PDF不需要子进程”变成原包通过。选择性延迟加载若要上游修正，必须另行评审，
不能算本轮系统兼容能力。

原始`agent/__init__.py`会先导入commands；`agent/commands.py:6,9`依赖selectors与
subprocess，因而直接import权限/策略/模式模块也可能在包初始化阶段失败。
`localpilot_api/service.py`又依赖agent，因此`security.py`的APIError导入也会先触发
整条链。须保存完整traceback，不能把观察到的首个ModuleNotFoundError当作依赖闭包。
[公开客体探针](../../../../tests/fixtures/modern2_runtime/python_dependencies.py)逐项尝试原包
及底层模块，不添加sys.modules替身、不改sys.platform、不改任何包源。

Pillow静态集成单独交付；其通过不能解锁上述进程/等待语义。

## subprocess与fcntl/select：实施前必须冻结的语义

| 真实调用点 | 最小机制与适配 | 首批真实客体gate（本报告未实施） |
|---|---|---|
| commands.py:63 Popen，:70 DefaultSelector，:72 set_blocking，:79 select | 受控子进程创建，独立stdout/stderr管道，非阻塞FD及有界就绪集合；原子检查与挂起、绝对单调期限 | 同一子进程交错输出两条管道且超过管道容量；父端并发排空、短read、EOF、超时、子进程失败；每次精确回收 |
| subprocess.py:1920 fork_exec | 绑定现有loader/进程profile的适配；真实exec失败的错误通道、cwd/env、CLOEXEC/close_fds、stdio转交 | 缺失ELF和错误格式必须在父端可区别；描述符不能泄漏；资源耗尽回滚；成功路径真实父子不同身份 |
| commands.py的start_new_session/killpg | PX1/PX2进程组、session与取消边界；不能把单PID kill伪装为killpg | 子进程再启动后代，超时/取消停止正确组；PID复用不误杀；部分外部作用不确定保持UNKNOWN |
| cli.py:47 flock(LOCK_EX|LOCK_NB) | 绑定真实打开对象的锁、同/跨进程冲突与退出释放；不是线程内字典 | 两进程竞争同一对象，第二进程真实EWOULDBLOCK；持有者退出/exec/close后的生命周期按契约验证；别名路径不能绕过 |
| selectors.py:12 import select | PX3文件/管道/终端就绪；网络接入后复用同一对象机制 | 空集合timeout、双向read/write、hangup/error、dup与close并发、无丢唤醒、无闲置忙轮询；pselect信号掩码另等PX1 |

现有`newlib_syscalls.cpp:912`有F_GETFD/F_SETFD、F_GETFL、受限F_SETFL与dup操作，
并没有flock文件锁或通用O_NONBLOCK。不能因为C fcntl符号存在就注册完整Python fcntl。
现有线程profile的fork/exec限制保持，不能为了_posixsubprocess取消多线程安全拒绝。
可先把只需既有FD操作的Python子集独立设计，但模块能力查询、未支持命令报错和具体
调用者所需的flock必须分开；本轮没有以此宣称CLI解锁。

## 可信文件身份与防链接：独立PX5设计输入

当前`newlib_syscalls.cpp:366`的stat由清零结构加0777模式合成，
`open_flags_to_file`拒绝O_NOFOLLOW/O_NONBLOCK/O_DIRECTORY等未支持标志。
`files.cpp`已有同一服务生命周期内的文件身份跟踪，不能据此推断跨重启稳定inode、
可信owner、权限执行或防路径替换。保持当前拒绝比接受后丢弃安全flag更准确。

| 要求 | 拟定真实边界与错误行为 | 最小验收 |
|---|---|---|
| 主体/owner | 由受保护文件会话的内核认证调用主体关联持久principal；定义principal建立/重启恢复/委派，不能把自报UID、进程名或统一0当身份 | 同UID不同主体/伪造身份/撤销会话拒绝；非owner读取0600被拒绝；退出不把旧主体误授给新进程 |
| mode与存储 | 原生可承载元数据的后端，或受保护且与文件身份/内容一致提交的元数据层；明确恢复、rename/unlink和崩溃边界 | create600、umask、chmod、父目录搜索权限、重启一致性；数据/元数据提交中失败不得暴露为可信私有文件 |
| fstat与对象身份 | fstat查询已打开对象；建议volume身份+对象编号+generation+服务恢复epoch；明确POSIX st_dev/st_ino的映射及持久性 | rename、unlink后旧FD、新建同路径、重启、服务重启；旧grant不能重指新对象 |
| 路径解析/dirfd | 文件服务持有稳定目录对象引用并逐组件校验，处理相对路径、..、大小写与FAT名称等价；路径授权不能只检查归一化前缀 | 替换祖先目录、路径别名、..逃逸、grant撤销与open并发；每个拒绝不泄漏打开句柄 |
| O_NOFOLLOW / lstat | 定义末组件不跟随；若后端无链接，必须能保证整个解析路径无链接/重解析穿透，不能只忽略flag；工作区beneath/祖先安全需单独规则 | 末组件链接、祖先链接、循环与竞争替换；lstat不跟随；不存在链接支持时显式能力与保留行为 |
| 审批/执行者 | 原security.py:19/70与workspaces.py:35/58的检查继续执行；绑定实际执行者/subject/scope、撤销及目录身份 | 检查至使用之间换对象、跨subject复用grant、可执行文件替换、非授权Operator请求均拒绝 |

FAT本身不能提供的语义必须先选择并验证后端/元数据方案。此处不认领files next op，
也不建议以构造stat结果、忽略链接、chmod空成功来换取import或服务启动。
文件机制负责人先提出独立版本化协议认领，再实施普通/线程SDK和服务；不能由应用分支抢号。

## 原API 1.0最终验收仍是独立门槛

导入`localpilot_service.protocol`及读取版本字符串，只证明原模块可加载。
真正原API 1.0须在同一原Core实现上验证受控HTTP/SSE请求、schema/能力协商、
断线游标/重连、持久任务与幂等、取消/安全恢复；再独立验证认证subject、会话/工作区归属、
Operator审批的请求/决定/执行一致性、跨主体及过期审批拒绝。
在途执行或提交发生故障时保留UNKNOWN、隔离与人工处理，不以重试声称未执行。
这些gate在N2、文件身份、select/subprocess等前置完成前均为BLOCKED/NOT_RUN，
不运行第二套Agent Runtime来替代它们。
