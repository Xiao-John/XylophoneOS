# 245042e2 · 独立部署和选择 glibc 应用 SDK

基于 `7c581be6`。项目已有 `create_xypm_profile.py` 和 `xos_app.py`
的显式候选构建路径。普通发行继续以 newlib SDK 为输入，已有 Linux
预览工具包所配的 sysroot 也是 newlib。本次交付从已绑定的目标 glibc SDK
生成可搬移的应用开发目录。

部署目录内含 sysroot、原始 SDK manifest、glibc/GCC 来源核验文件以及
profile。复制后重新核验绑定。目录自己的 `xos-app` 选定这套 SDK 和
profile，再调用原应用构建入口。部署依赖 manifest 中记录的配套交叉工具，
这些工具由宿主提供。原 `xos_app.py` 的文件摘要也由旧应用回执绑定，因此
把选择逻辑放在独立启动器里。两套包使用不同 profile 与工作盘。
[部署命令](../contracts/xypm_sdk_profiles.md#独立部署-glibc-应用-sdk)

## 实际构建及应用

在 Linux arm64 上从锁定并验证上游签名的 glibc 2.44 源码重建 C SDK。
组合此前通过 #231 验收的 GCC 16.2 POSIX C++ 归档、头文件和签名回执。
重核工具、编译器运行库、原 C++ profile 与逐文件摘要。两份 C 公共头集合
唯一变化为 `gnu/stubs.h` 移除 `__stub_select`。组合后重新生成并核验 profile。

从独立部署归档在另一台断网容器解包，宿主只挂载归档与应用夹具，交叉工具
使用和构建一致的容器镜像。通过部署目录的入口初始化、构建、检查和打包
外部 C/C++ 应用。C-only SDK 也通过部署、构建和检查。正常系统
`c98b472517892e6d` 在私有 FAT32 工作盘离线
安装两份应用。C 读用户文件并报告 glibc 2.44，C++ 使用 `std::vector`、线程 join 和
异常处理。进程退出后回到 129654 空闲页、7 个任务、1 个完成记录。

启动器拒绝其它 SDK 参数。应用工具拒绝其它 profile 的工程和已被改动的
linker script。包工具拒绝用冻结 profile 验证 glibc XPK，以及向冻结 profile
的工作盘安装该包。拒绝操作后原工作盘摘要相同。

## 回到冻结 newlib

用 `0.0.1-1024` 发行 SDK、原 profile 和原应用驱动构建冻结对照包，在使用
glibc 前将其安装到独立工作盘并执行。切回冻结 SDK 后，执行原 ELF 并
核对原工程回执，再次打包得到逐字节相同的 XPK。同一工作盘保留初始用户文件
和第一次运行追加的 `before`，旧 ELF 再次启动后追加 `after`。正向运行均
回到同一资源基线。

## 存量包复验

同一 ISO 运行 #231 已留存的 `daily-runtime.xpk`、原 profile 和原 dash。
原测试在 `demo quiet` 条件下执行完整 13 工具场景，输出 `DU12_OK`。
破损包拒绝、非托管文件冲突保护、离线安装、运行与管道、同步和安装内容
核验、卸载与用户文件回读六项通过。profile 宿主测试 45 项通过。

## 双入口与冷启动进程槽

两轮 dash 复验使用同一 ISO、应用包、dash ELF 与脚本。默认启动的 `ps`
显示 `heartbeat`、`spinner`、`receiver`、`sender` 四个演示进程以及
音频、文件和 xsh，共占 7 个槽。xsh 启动 `/usr/bin/dash` 占第 8 个槽。
dash 的第一个普通子命令 `kit_c` 报 `EAGAIN`，子进程未进入启动事件，
dash 以 126 退出。默认启动失败出现两次。相同默认条件下 xsh 直接执行
两个应用成功，每个应用只需要一个额外进程槽。

内核 [`tasks.cpp`](../../src/kernel/arch/x86_64/tasks.cpp) 定义八个进程
记录。`sys_process_create` 在无法预留进程记录时返回资源不足，
[`spawn_support.cpp`](../../src/ports/glibc/spawn_support.cpp) 将创建
阶段的该结果映射为 `EAGAIN`。在既有 `demo quiet` 条件下，剩余 3 个
任务，dash 通过 PATH 启动 C 应用，通过显式路径启动 C++ 应用，正常退出
并恢复到 129698 空闲页、3 个任务、1 个完成记录。默认冷启动的并发进程
容量仍是切换门禁中的独立条件。

| 输入与回执 | SHA-256 |
| --- | --- |
| 签名 glibc C SDK manifest | `910945af68004d26e0778738115588ebde0eca05a5f69f635758fc56fa1a67fa` |
| 组合 C/C++ SDK manifest | `45ec2bc96ef7b26f4d035fd1aa7ed424bf6efba55164b06ee89ebec8e19fef50` |
| profile | `1dd89afc949f21a3ae07b2de617ae3319b590341b68870e7dd836563822c31c9` |
| 部署归档 | `d536766a011a2ea0480cc1a4be7bffb4e0eaa627e6214ba3acad9958f234c122` |
| 正常系统 ISO | `0b6ca54b7a27290eebd4e536b806dfd0059ac7fd21d1c4ea38beab32ef4422eb` |
| 正常系统 manifest | `4fb6e08f03e7a5fd18a474050e70864231a4a200fdcef814011c52af8eda429f` |
| C XPK | `2cfa12a5a5386ab1a8bfcf69c1badfcf9b54ae52757b421420d5dbb821239208` |
| C++ XPK | `2f1052f5dc69eb88bac4230ea26348b8b821f22d2da2ee12a67e93613a5a9a0b` |
| 冻结 newlib 发行 SDK 归档 | `86583de2a13b3eea095e94e3768243fdb40216bdfb7e01bc8909d969331e5f66` |
| 冻结 newlib 对照 XPK | `e0b0c134d4beec862a2e6647363755df6cc5263f250e6374064c38fa44195819` |
| 三轮选择/客体验收回执 | `0224f1678c33f55ca6f8e4d8dd3cc0cff7d2fb4a6187069f088e4f11ebaad792` |
| 原 #231 日用工具 XPK | `1db19322504263435da3a952e952328530cccd226f6a8a94905a29aff35b3827` |
| 原 #231 日用工具重验回执 | `5a94b18b955601ab0abcac80482b1038b30c2b7d4a9f02c6c1b4e9068f10e6ee` |
| 默认冷启动 dash 失败回执 | `db02cb4a1c223044b0353aef7265ece76064d6588a02244512f795904698b1db` |
| `demo quiet` 双应用 dash 回执 | `7dcbd03dae453fdaebfa29edccfd0fb923e1ea825b32da15f52f6017bdce5eed` |
