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
