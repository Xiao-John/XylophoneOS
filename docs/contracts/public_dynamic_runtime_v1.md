# 公共 GNU 启动闭包 v1

本接口把已批准动态 generation 接入普通 native SDK 的文件检查、spawn、wait，
以及对应共享 glibc 的 `posix_spawn` 和 `execve`。批准边界、同一文件 pin 与
易失激活目录见 [dynamic_closure.md](dynamic_closure.md)；对象编码见
[dynamic_admission_v1.md](dynamic_admission_v1.md)。本页描述源代码契约，具体
构建是否通过客体验收，以绑定其完整输入和输出摘要的 report 为准。

## 入口与权限

受信原生控制器显式调用 `dynamic::install(policy, absolute_deadline)`。
这个强引用从可选 `libxos_loader.a` 拉入公共动态入口；未调用它的旧静态程序
只保留普通静态入口中的弱引用。静态 supervisor 不需要链接整个动态闭包实现。
SDK 中的头与 archive 必须来自同一构建，不能用复制新头的方式升级旧 archive。

成功安装之后，普通 `execution::inspect`、`spawn_file`、诊断及 receipt 变体
首先尝试当前已批准 main。只有经过批准 manifest 验证后确认 main 精确路径
不同，才允许 `not_selected` 静态回退。损坏的动态程序、撤销、超时和错误的
路径不能借此降级到未经批准的动态入口。

`dynamic-run SLOT /absolute/main [args...]` 是可安装的原生控制器。其批准根
来自构建时显式列出的二进制 generation；运行时不从相邻 JSON 推导批准。
启动时完整验证默认根，再按需激活指定 slot，然后走上述普通 SDK API。
它通过 `copy_from_caller` 继承调用者已有的进程创建权限，所以有权创建子进程
的普通应用可以继续 `posix_spawn`；它不为没有该权限的调用者创造权限。

## 真正的 ELF 检查和启动

每个对象的文件长度、完整 SHA-256、原生只读 NOTE 和以下 ELF 信息均从同一
readonly pin 读取；之后映射和转移仍使用这些开放描述，不能重新打开路径。

| 项目 | 公共闭包要求 |
|---|---|
| 平台 | ELF64 little-endian x86-64；OSABI 0/3 均要求精确 XOS 身份及 SDK ABI |
| 几何 | 有界、页不重叠的可读 LOAD；检查偏移、对齐、映射 span、主程序 PHDR |
| 权限 | 拒绝 W+X、可执行栈、text relocations；要求 GNU RELRO |
| 依赖 | 实际 `DT_NEEDED` 的顺序和索引必须等于已批准图；实际 SONAME 精确匹配 |
| 符号 | 有界 SysV/GNU hash、dynsym、字符串与 GNU 版本表；跨对象版本提供者匹配 |
| 重定位 | 只接纳实现的 AMD64 RELA/RELR 种类，检查目标可写范围、符号索引及 IFUNC 入口 |
| TLS | 检查 PT_TLS 文件/内存长度和对齐，随后由 GNU rtld 建立初始与线程 TLS |
| 搜索 | 闭包限定查找；未知 dynamic tag、RPATH/RUNPATH、缺失依赖等拒绝 |

bootstrap 自身继续受普通静态 ELF 装载器及 128 KiB 文件界限检查。控制器把
已验证映射计划、固定批准根、选定 generation、已转移 pin 和启动控制描述
写入只读 capsule；客体不能修改 capsule 后把新字节当成批准结果。
capsule 的内部布局版本为 2，固定从 `0x71000000` 开始；它位于线程 stack/TLS
保留区 `[0x70000000, 0x71000000)` 之后，并在初始进程栈之前。编译期检查
同时排除静态 TLS、进程 heap、DSO 映射区和早期 GNU heap；动态闭包预检还
拒绝 bootstrap 的 LOAD 覆盖 capsule 或线程区域。普通静态 ELF 的历史地址
兼容性保持原定义。公共 native NOTE 的 ABI 摘要绑定 C SDK manifest 和上述
启动 ABI 头文件内容，防止旧 capsule 与新地址的运行时混用。

bootstrap 用同一开放描述映射 main 与 interpreter，准备 argv/env/auxv、
GNU 初始栈及 Files 会话，再进入真正的 GNU `ld.so`。早期 heap 固定为 8 MiB，
位于 `0x1fff00000000`，与生成的 DSO 映射区间分离。其余库从已转移的 pin
加载。重定位、IFUNC、TLS、DSO 与主程序构造函数全部完成后，共享 libc 的
初始 `__libc_start_main` 路径通过启动控制协议发送唯一 READY，并等待经认证的
ACK 后才调用 `main`。内部 unwinder 对已有库的 `RTLD_NOLOAD` 初始化不会重发
READY，构造函数中创建线程也不会提前发布启动成功。错误路径发送对应失败
阶段；启动者据截止时间清理仍未就绪的子进程。

## libc、文件描述符和 exec

共享 glibc 接收 native Files 启动会话和同一批准政策，公开 `posix_spawn`
使用普通动态 SDK 路由。FD 快照保留相同开放描述的别名和共享游标，过滤
`FD_CLOEXEC`，继承 cwd 和环境；父进程的 FD 表不会因 spawn 清理而改变。
kernel console、已路由到 stdio 的 pipe，以及普通 Files 描述可进入 v1–v3
启动布局。socket 和未路由 pipe 不能被伪装成其他描述符。

普通 v3 spawn 的 pipe token 属于父进程；`sys_process_stdio` 只把它转成
子进程的固定 kernel route，不能把父 token 原样交给子进程读取。loader
按开放描述对象把所有别名转换为同一子 route，并在启动前关闭没有被快照
引用的重复 route。因此关闭最后一个 FD 时立即释放子 pipe 端点，不依赖
进程退出产生 EOF。`FD_CLOEXEC` 记录不进入新 FD 表，父进程的表与 token
所有权保持原样。若一个 kernel route 仅剩 fd >= 3 的别名，原 POSIX stdio
已关闭，loader 可借用空闲的同方向传输 route；它不会把已关闭的 stdio
重新加入子 FD 表。该传输机制只有一个读取 route 和两个写入 route，最多
32 个 FD 是快照及别名数量上限，不表示可继承 32 个独立 pipe 对象；未路由
pipe 继续在 glibc bridge 明确返回 `ENOTSUP`。同 PID `execve` 保留既有
token，不能套用普通 spawn 的 route 转换。旧静态 v1/v2 降级的准入条件也
保持不变。

`build_spawn_pipe_probe.py` 的默认模式明确记录为 `diagnostic_override`，
用于把所选真实 loader 对象显式链接到一个有独立 SDK 双锚的诊断程序。
最终 SDK 门使用 `--sdk-loader`：核对 SDK 输入记录和随 SDK 分发的
`load.cpp` 摘要与受测源码完全一致，只从已验证的 `libxos_terminal.a`
链接，不插入 loader override。两种模式的 receipt 与执行报告分别保留。
同一个公共 C 夹具也可构建为 `p0pipe` 批准根，由公共动态运行时矩阵的
第九场 `c-pipe` 真正启动；最终报告导出加 `--require-pipe` 强制要求该场通过。

`execve` 使用真实 kernel image replacement。新闭包完整预检后，旧进程先
向原启动控制器发送 PREPARE，并获得新 generation/nonce 的 ALLOW。新映像
继续使用同 PID、原有 Files 所有者及明确保留的控制通道。commit 前失败，旧
映像保留 FD 和游标，通过 CANCEL/ACK 取消 pending 转换；commit 成功后旧
代码不再返回，新映像完成自己的 READY/ACK。

父控制器的普通 `sdk::wait_flags` 持续驱动认证控制消息，因此应用可以在
等待期间执行多次同 PID 替换。身份元组、nonce、generation、artifact 摘要
和 deadline 都需要匹配；不能仅凭 PID 或一个 READY 字符串宣布启动完成。

## 构建入口与独立锚

使用 Preview2 开发工具和已经验证的 C SDK。以下路径为调用者明确选择的
输入/输出目录；SDK 两个摘要必须从独立已批准的发布记录取得。

1. `build_glibc_shared_runtime.py --public-startup` 要求
   `--sdk-manifest-sha256` 和 `--sdk-tree-sha256`。它在完整 SDK 快照复制前后
   及构建结束时验证两个独立锚，并验证 GNU glibc/GCC 原始来源签名。公共
   构建运行普通 GNU `make lib`，没有私有 `rtld-routines` 替换；profile 仅
   排除不支持的 hosted audit 模块。native NOTE 在正常链接时加入。
2. `build_glibc_shared_gcc.py --public-runtime RUNTIME_BUILD` 构建共享
   `libgcc_s`、`libm`、`libstdc++`，并把其 libc/interpreter、CRT、头文件和
   native ABI 绑定到同一 runtime。不能混入其他 SDK 的 C++ DSO。
3. `build_dynamic_program.py` 接收 C SDK、native SDK、public runtime、实际
   应用源文件以及可选 C++ 依赖库源文件。C SDK 和 native SDK 分别要求
   manifest 与完整树两个独立锚。输出真实 PIE、bootstrap、DSO、文件清单
   和二进制 generation，随后运行生产 ELF 检查器的离线完整预检。
4. `build_dynamic_launcher.py --system SYSTEM --system-source SOURCE` 接收
   同一 native system/SDK，以及 `--generation LOCAL_BINARY GUEST_PATH`
   明示的一至四个根。每个根都进入只读编译头。C SDK 同样要求两个独立锚，
   native archive 还校验实际成员归属。输出 ELF 和可审核的 build receipt。
5. 按 program manifest 的 `files` 清单安装闭包和 generation，并安装该
   launcher。对共用路径的不同字节必须拒绝。常规命令随后可调用
   `dynamic-run 0 /apps/example/main`，或经 dash 脚本启动同一入口。

builder 的 `built_not_run` 只说明构建及离线检查完成。真正的执行证据由
`tests/public_runtime_guest.py` 绑定 system source、完整 native/C SDK、GNU
runtime/source、C++ 依赖、程序 stage、批准 launcher 和 shell 工具，运行
真实 C/C++ 程序并检查退出状态及精确资源恢复；客体结束后重新检查所有输入。
构建 receipt 不会被回写为测试通过，也不会把旧 report 移绑到新字节。

## 当前范围和下一阶段

默认 profile 的运行期 `dlopen`、`dlmopen`、`dlclose` 明确执行固定启动闭包政策：包括
`dlopen(NULL)`、已经加载的库和新 namespace，均返回 profile 错误并提供
可读取、可清除的 `dlerror`。显式构建的独立 online profile 及其 generation
v2、namespace、pin 和动态 TLS 边界见
[online_libraries_v1.md](online_libraries_v1.md)，不能用它扩大默认 profile。

批准目录是每个控制器内有界、易失的状态，支持完整预检后激活、批准回滚、
expected sequence 和撤销。失败保留旧 active；已经捕获的 pin 不会被换成
另一份文件。只读 capsule 继承的是启动时政策快照，不是跨进程实时撤销协议。

持久全局目录、断电恢复、跨后代撤销广播、动态 fork→exec 的父控制权迁移、
超出 online profile 已声明范围的在线装卸及组合，以及 terminal actor 的
完整动态 exec 组合仍需独立 P1 契约和资格。普通 console/pipe/Files stdio
与 terminal actor 是不同启动协议，
不能把前者的成功报告扩张为后者已通过。
