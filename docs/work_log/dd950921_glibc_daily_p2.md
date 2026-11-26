# dd950921 · glibc 日用包原生维护

从 `a2e5cb45` 对齐目录/路径、dash 外部命令重定向和日用包。使用新构建的
glibc 2.44 C SDK 和已核验的 #214 C++ 闭包装配候选 SDK。glibc 与 GCC
源码证据经过现有 profile 准入核验，编译器和 binutils 摘要相同。C++ 复用件
为原有 libstdc++、libsupc++、POSIX libgcc unwinder、对应头文件及许可材料。
当前 C 头文件的差异为 `PIPE_BUF=4096` 和生成的 libc stub 列表。目录接口和
文件描述符接收对象随当前 SDK 重新构建。

`xos-x86_64-glibc-static-daily-preview-v1` 同时要求目录、C++ 运行时和
`stdio_transfer`。13 个 C 工具、dash 与 C++ xypm 使用同一候选 SDK 和
profile。原生 P2 继续按构建时的单个 profile 接受软件包。冻结的 newlib
profile 在宿主核验入口拒绝此候选包。

| 构建与交付输入 | SHA-256 |
| --- | --- |
| 签名核验的当前 C SDK manifest | `859004e358f8b7dff968a659cb3e02e697102f6005fa0fb4e40c0f72ffca64c7` |
| #214 原 C/C++ SDK manifest | `a4a6b3c278e34773088b11bb2a352d96487b9234755b9fcb9c7fe96ab9ace96e` |
| 同一候选 C/C++ SDK manifest | `a9490cc126053b9e15808533e388f9d780ce0bc8e9b48ae71f3926932dfdfbdc` |
| profile 文件 | `0e54420be8a9bc2f98e740c92f51c3d728021f940e356aeddf31b07b29858b9b` |
| 正常系统 `a25c7d37c6069d60` ISO | `2a057a756f39b863b4fa91cc88331ba383f531f11b1d3b24536ad369cf998e7d` |
| xypm ELF | `77086d0abcc497868bb253f9f008757e51fe142d30a3ad5b1073a75c35f0377f` |
| dash ELF | `7dfabd45670c8164f62075b6f36633d7b91e9590748056c7cfdbc3e775fe57b9` |
| 完整工具 XPK | `97b0af529be3b75406bab24a71030acc4badfec0e128bcb55edbd75db8c0893b` |
| 精简运行工具 XPK | `1db19322504263435da3a952e952328530cccd226f6a8a94905a29aff35b3827` |
| dash + 精简工具包 + xypm 候选 ISO | `5d6e307b9fb29dd8b54b108d1351451703a020b2bd7793a948cf7e82fdfd661d` |


## 客体内 P2 验收

QEMU 11.1.3 在独立 FAT 盘上使用正常系统镜像。无维护租约的安装请求被
拒绝。随后使用带预期 XPK 摘要的 `maint-run` 原生安装精简运行包，提交后
由镜像内的恢复程序清理事务。关机后读取全部 26 项安装内容并核验摘要。
重启执行原 `du12.sh`，13 个工具完成且 33 份输出逐字节相符。

再次使用原生 `maint-run` 卸载，检查已安装包记录为空、26 个受管理文件
和事务目录已清除。安装前已有的用户文件、安装后放入包目录的非托管用户
文件及 DU12 输出均保留。拒绝、安装、运行和卸载前后的资源计数为
129795 个空闲页、2 个任务、0 个完成记录。原生 P2 回执 SHA-256 为
`11752459acbe2e29839aacb4d93880c71bf6c7d1e42fa5b61ae59dea34a23ddb`。
[原生维护门禁](../../tests/daily_utilities_p2_guest.py)

## 可选 ISO 有效载荷

完整包连同 dash 和 xypm 打包需要 45,563,272 字节，现有 XOSBND1 v1 的
33,554,432 字节限额拒绝这一组合。可选
[运行文件暂存入口](../../scripts/stage_glibc_daily_runtime.py)
用 SDK 绑定的 `objcopy --strip-debug`，将保留的 38,230,056 字节完整工具
ELF 转为 8,761,224 字节运行 ELF。具名节表的文件偏移、节数和节名表索引
可随移除调试节更新。暂存核对 ELF 入口、全部程序头、其余 LOAD/TLS 字节和
只读 `.xos.exec` 声明。13 个精简 ELF 均保留符号表，完整 ELF 含 DWARF。
原工具、链接回执及完整 XPK 可用于回溯调试。

用现有打包器得到 8,929,280 字节 XPK。包含完整 dash 与 xypm ELF 的
XOSBND1 为 16,092,552 字节。ISO 使用现有类型 3 暂存包及类型 5 提供
xypm ELF，无需扩大容量或更改默认镜像。profile 核验宿主套件 45/45 通过。

在原启动顺序的冷启动中，客体校验并暂存了三个 XOSBND1 成员。随后监督进程的自动安装
收到 `maintenance: busy or denied error=-11`，并报告会在下次启动重试。
这一拒绝发生在包管理器启动前。内核的维护准入要求仅监督进程和文件服务
存活，当前启动顺序会在自动维护前启动音频服务。手动 P2 门禁使用已有的
`demo quiet` 与 `audio stop` 完成准入。调整启动顺序后，同一 XOSBND1
载荷冷启动通过自动安装和恢复清理，关机后核对 26 个文件及三个暂存成员。
[冷启动复验](03c0fe80_install_bundle_before_audio.md)
[监督进程启动顺序](../../src/user/programs/supervisor.cpp) ·
[内核维护准入](../../src/kernel/arch/x86_64/tasks.cpp)

## 提交边界和冻结对照

通用 SDK 接收对象、profile 准入和打包器可独立合入。全量和精简产物共享
同一 SDK、profile、13 工具构建来源、v1 包格式和原生 P2 实现。可选暂存
提交和本回执独立于通用打包入口。

[通用打包回执](907ccb19_glibc_daily_xpk.md)记录了旧、新打包器使用同一份
冻结 newlib SDK、profile 和工具进行逐字节对照，两者 XPK 摘要均为
`ecadaad4e4d85790c3c5eb8d0fc63caf4823ab83baea43aa424a90710fce21e8`。
#214 在冻结 newlib profile 下独立构建并以普通维护命令复验八项事务。
其 xypm ELF 摘要为
`3def19bd47a56d4eee0d4a14d761fcb2b44593cbe2cd940db82eac710877e3e4`。
本轮使用新的正常系统和显式 glibc 候选做日用包验收。对当前候选包使用冻结
newlib profile 的宿主命令，结果为目标 profile 不匹配。
