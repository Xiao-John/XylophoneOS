# 68d0481f · glibc 显式路径启动与子进程等待

静态 XOS glibc 的 `posix_spawn` 通过现有原生 ELF 加载器创建进程。加载器沿用文件
内容固定、ELF 解析、页映射、TLS 准备和失败撤回流程。文件读取走 libc 现有的受认证
会话。传入的 `argv`、`envp` 和当前工作目录交给原生启动协议。父进程已有的创建权
限由现有系统规则处理，普通启动路径不会提升权限。

本次支持显式绝对或相对路径、默认属性、空文件动作及阻塞模式的原生标准输入输出。
参数和环境遵循现有 XOS 启动上限，分别最多 64 项，单项最多 255 字节。
缺失或标记 `FD_CLOEXEC` 的标准描述符在子进程中关闭。额外的非 `FD_CLOEXEC` 描述符、
文件动作、非默认属性和超出支持范围的标准描述符返回 `ENOTSUP`。已有标准描述符在
加载期间保持有效。`chdir` 和进程加载互斥，确保相对路径和继承目录一致。

`waitpid` 支持正 PID 和 `-1`，含阻塞和 `WNOHANG`。`wait` 使用同一条等待路径。
`pid == 0` 和 `pid < -1` 是 POSIX 进程组选择器，当前 XOS 返回 `ENOTSUP`。
正常退出保留低八位，XOS 异常终止沿用 newlib 的 `SIGKILL` 状态投影。已回收或非本
进程的子进程状态返回 `ECHILD`。进程组、停止与继续状态、PATH 搜索、文件重定向、
`fork`、`execve` 和 Linux 进程 ABI 仍在后续范围。包管理 `spawn_delegate` 需要
独立资格。本次复用现有进程和文件协议。

## 验证

[来宾门禁](../../tests/glibc_static_guest.py) 的 `process` 套件使用新建的 glibc C SDK、
正常系统镜像和该系统的 newlib dash 回执。xsh 普通程序入口和 dash 脚本入口从同
一 glibc ELF 创建子进程，检查退出 0 与 23、`WNOHANG`、继续等待和重复回收失败。
xsh `exec-file` 的无创建权入口验证 `EPERM` 及无子进程状态。夹具同时检查目标缺失、
普通数据文件、描述符继承限制、原生权限和每轮进程资源恢复。

| 初次绑定与套件 | 结果 |
| --- | --- |
| 系统 `cbf62f2779d0fcbd` | ISO `85a5a5ccf383a87136bc388ed32d07700aa8525a74146b994f43e168b84b5f12` |
| 经签名校验的 glibc 2.44 C SDK | Manifest `2e48a986d71478f82899e7480195056b2a739a4beaf808ae58819ffc91132ce3` |
| 测试 ELF | `6c993a78e5e981d0c60fc9c82f4b3de2a8780d3a5ae3320a739294dcdbb87922` |
| QEMU 11.1.3 常规 BIOS 客体 | xsh 常规、xsh 拒绝及 dash 各两轮通过，资源恢复至 `[129700, 3, 1]` |
| 既有回归 | `cwd` 双入口各一轮通过，另通过文件运行库 47 项宿主及 14 组真实 files/FatFs 集成检查 |
| 来宾报告 | `82e4332a442a37e56848d792d163622a179dd35d8389b7b9cdeac229cc4aa01a` |
| 串口日志 | `c0137dce2d27d7428c6769e1c81f0abfebf1ce0958b628bc6964bd0926e51167` |

## 与文件查询修复合并后的复核

在 `ae7598e4` 上移入 `c8e893d6` 的进程实现。`access(X_OK)` 继续通过单次
files stat 请求完成。SDK 保留启动所需的 `elf.cpp`，库成员仅有一份检查器，并省去
旧的客户端 ELF 检查桥。`posix_spawn`、`waitpid` 及 `chdir` 序列化实现沿用原进程提交。
系统 files ELF 链接纯检查器。真实启动继续由调用方和加载器负责。

| 合并后的验证绑定 | 结果 |
| --- | --- |
| 系统 `4e9f3ff3d50be5b8` | ISO `667fc1ed609bba317d5b5a285d546b161b7f8d9cd58423aea4cd99736a92f21e` |
| 签名校验的 glibc 2.44 C SDK | Manifest `e6fd644f5c8717ea67877fb58d6ed1118703913d3ce77fc70e05cd98ffb2ab58` |
| `cwd` QEMU 11.1.3 | xsh、dash 各两轮通过，报告 `a7d64341c6c381eecfb9bcbba78867302dc39d97aba4ccb7c42a6924ae13c651` |
| `process` QEMU 11.1.3 | xsh 正常、xsh 拒绝、dash 各两轮通过，报告 `c4ede383867a1f3e3777b01387ef2f9621279e4e38ce270dc029643012b63390` |
| 两组资源基线 | `[129698, 3, 1]`，十轮均恢复 |
| 宿主文件回归 | 48 项检查及 14 组真实 files/FatFs 集成通过 |

## 文件交换序列化复核

`files` op26 把零或当前 PID 解释为修改自身目录。glibc 公共 `chdir`、
内部路径入口和通用交换入口现以相同锁序处理自身目录变更，先持有启动目录锁，
再进入 files 会话。加载器在启动目录锁内以 op26 设置受调用方所有的子进程目录，
该请求仅持有 files 会话锁。files 服务继续验证目标子进程和初始化状态。

宿主回归在持有启动快照时执行子进程目录设置，并验证 `chdir`、零目标通用
请求和显式自身 PID 的原生客户端请求均等到快照释放后才发出。进程客体在真实
子进程仍存活时验证 `0`、`-2` 的 `ENOTSUP` 和状态保留，之后以指定 PID
和 `-1` 正常等待。

| 复核验证绑定 | 实测 |
| --- | --- |
| 正常系统 `501f0120fbb8751b` | ISO `f766ec17d5276cbcdf46c25469c5368bb01ead43636341b9f8266c4876d974f3` |
| 签名校验的 glibc 2.44 C SDK | Manifest `1d516751a2169d525a6f3328a7904a1d248d7b2d4d739b5752dd3af6bed27335` |
| C SDK 压缩包 | `9bedbc09c16ecdfb6da7bbd180f02aa2ecbfec1a84612fb426553e879af6839d` |
| `cwd` QEMU 11.1.3 | xsh 与 dash 各两轮通过，报告 `5b819c4d493bfd91643da2f1e82eae88b03fa59997e6750a3b0463dfed3e04dd` |
| `process` QEMU 11.1.3 | xsh 正常、xsh 拒绝、dash 各两轮通过，报告 `850d4245e2ba461642b0e7f96043bdb02714fe108af5f1be187a5f7b55729acc` |
| 两组资源基线 | 十轮均恢复至 `[129698, 3, 1]` |
| 宿主文件回归 | 49 项检查及 14 组真实 files/FatFs 集成通过 |
