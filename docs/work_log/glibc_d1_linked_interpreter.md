# glibc D1 原生 GNU 解释器和共享 libc

这个组合接续 #295 的已认证依赖闭包和 #305 的固定启动策略。XOS bootstrap 以同一文件会话验证、读取并映射 GNU `ld.so` 和应用，然后以私有入口栈跳到实际 GNU `_start`。GNU `dl_main` 从已授权 pin 装载 `libc.so.0.1`，完成重定位、TLS、RELRO 和晚期文件运行库交接，再交给 GNU `Scrt1`。

真实 GNU x86-64 libc 包含 IFUNC，因此 GNU 链接器输出 `ELFOSABI_GNU`。固定闭包的对象读取来自已认证 pin，支持 SYSV 和 GNU ELF 格式的 ABI version 0；未知 ABI version 仍由 GNU 检查拒绝。对象的原生身份、generation 和批准摘要由 D0 的可信启动记录负责。正式动态入口的 `dl-sysdep.c` 守卫保持有效。

## 构建和运行范围

- `ld.so` 和 `libc.so.0.1` 使用同一验签 GNU glibc 2.44、目标工具链和 C SDK。共享 libc 链接选用该 SDK 来源对应的 PIC terminal、loader 和进程支持。GNU 常规共享链接启用 `-z defs`、立即绑定和 NX stack。同批 GCC 16.2.0 的验签源码提供真实 `crtbeginS.o` 和 `crtendS.o`。
- 有限 C 用例由外部 GNU 编译和链接，依赖 `libc.so.0.1` 的 `GLIBC_2.44`。QEMU 验证构造函数、普通环境、auxv、文件服务中的磁盘读取和 errno。
- C++ 用例使用相同共享 libc 和 GCC PIC CRT，验证构造函数、主线程 TLS 和正常退出执行的析构函数。共享 libstdc++、动态 unwinder、跨 DSO 异常及更多线程仍待验收。
- 授权负向保留同一合法 libc 文件及应用，给 GNU rtld 提供空闭包。GNU 装载失败返回 127，前后资源回到相同基线。先前的临时运行也记录了缺少正式 stdio 接收资格时既有启动器拒绝重定向，当前 C 用例在进程内打开文件。

原生 ready 通知、发布 identity 和激活清单、软件包 profile、继承 FD 的完整动态启动和 D1–D4 其余组合需要各自客体验收。当前结果保留在受控诊断闭包范围内。

## 重建验收

在实际主线 `af47b2c5` 上合入 #305 依赖，从组合 `41b1c4ee` 的 Git 归档重建。C SDK 收录 #306 的 loader 头文件材料，native PIC 支撑复用这份 SDK 的确切编译输入。正式守卫的错误与独立 GNU 最终链接各有回执。

| 用例 | 实际结果 |
| --- | --- |
| GNU C 程序 | 构造、环境、auxv、磁盘文件与 errno 通过，退出 0 |
| GNU C++ 程序 | 构造、主线程 TLS 与析构通过，退出 0 |
| 同一 C 程序与无授权 pin 的真实 libc | GNU 拒绝装载，退出 127 |

三组都运行在系统 `fe13f33a2c08aa13`，资源均恢复 `129696/3/1`。精确重建产出的 `ld.so` 和 `libc.so.0.1` 与首次成功运行的二进制逐字节一致。[构建绑定](../reports/glibc_d1_linked_interpreter_20261127/binding.json) · [C 客体](../reports/glibc_d1_linked_interpreter_20261127/c.json) · [C++ 客体](../reports/glibc_d1_linked_interpreter_20261127/cpp.json) · [缺 pin 客体](../reports/glibc_d1_linked_interpreter_20261127/unlisted.json)

`tests/glibc_d1_linked_interpreter_guest.py` 接受实际系统、C SDK、GNU 链接目录、已绑定的 dash 和 GCC PIC CRT，生成每轮构建命令、动态版本信息、QEMU 串口和资源计数。公开报告用 `${XOS_*}` 变量记录宿主路径，绑定中保留原始报告 SHA-256。

从草稿源提交 `2499f7a5` 的完整 Git 归档复建，系统 `8d8d22c07d5f48d2` 上三组再次返回 0、0、127，资源仍为 `129696/3/1`。对上游补丁上下文的收窄留下逐字节相同的 C 源码、`ld.so`、`libc.so`、GCC PIC CRT 和应用 PIE。SDK 与系统的回执使用本次新构建。[发布补丁文本复验](../reports/glibc_d1_linked_interpreter_20261127/publication_replay.json)

## 当前主线合入复验

在主线 `8d1b985d` 上叠加本分支并修复两处兼容问题。v3 的 FD 记录由六个 32 位字段组成，表按其自然对齐读取，保留旧静态接收器对四字节对齐的支持。范围关闭在已核对 FD 上限后显式转换索引，恢复既有严格编译选项。宿主对照确认旧索引转换被拒。单独修正该转换后的对照仍拒绝四字节对齐的有效 v3 表。最终 ASan/UBSan 验收通过 50 项文件状态机用例和 15 组真实 Files/FatFs 集成用例，宿主试验替代内核传输。

从精确源码 `5cac399d` 生成验签 C SDK 和正常启动镜像 `e8067c409e9b9629`。同一镜像完成八个静态套件、55 次用例，覆盖 C 初始化和现有 newlib 对照、文件和 v3 exec、FD 批量关闭与管道、路径、cwd、进程和终端继承。cwd 与进程套件同时使用 xsh 和当前系统 SDK 重建的 newlib dash。普通环境名和加载器控制名另外走 11 项宿主检查。静态文件服务故障镜像属于单独的门禁。

同一 SDK 和 ISO 重建了 GNU 解释器和共享 libc 的诊断组合。真实 C、C++ 程序退出 0，缺少 libc 授权的对照退出 127，三项均恢复到相同资源基线。官方 `dl-sysdep.os` 编译仍触发启动守卫。初次宿主绑定卷上的 SDK 头安装、lwIP 准备和 GCC CRT 抽取失败记录来自同一源码，完整目标构建在原生临时卷重跑成功。

[当前主线构建、客体和原始回执绑定](../reports/glibc_d1_linked_interpreter_20261127/current_main_replay.json)保留镜像、SDK、工件与四个离线快照的完整摘要；此前的独立诊断回执仍可使用各自的精确输入复验。
