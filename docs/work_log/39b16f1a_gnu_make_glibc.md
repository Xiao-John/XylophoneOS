# 39b16f1a · GNU Make 4.4.1 的 XOS glibc 端口

在 `e783fce2` 上增加独立构建入口 `scripts/build_gnu_make.py`。目标程序
使用 GNU Make 4.4.1 的原始解析器、依赖图和 recipe 调度器，编译为
`x86_64-unknown-xos` 静态 ELF。构建核验 GNU 归档、分离签名、发行主密钥、
glibc SDK 和交叉工具。目标程序由 `/usr/bin/gmake` 调用 recipe shell
`/usr/bin/dash`。
[构建方法](../../src/ports/gnu_make/README.md)
[来源锁](../../src/ports/gnu_make/source_lock.json)

原 sbase Make 的 `scripts/build_make.py --sdk build/sdk` 路径仍可显式构建。
`b906acbf` 上的 newlib 系统 `071adb4852ebe0e0` 和 sbase 目标都已重建。
[旧入口构建回执](../reports/gnu_make_glibc_20261126/legacy_build.json)

## 与 XOS 机制的边界

| 面向 | 本次处理 |
| --- | --- |
| 进程创建与等待 | 采用 glibc 的即时错误 `posix_spawn` 和 `waitpid`，保留 XOS 的创建权继承。GNU Make 使用定额本地并发，`-j2` 由两个必须同时可达的子任务检验。 |
| 标准描述符与终端 | 在单线程 GNU Make 内保存文件描述符及 close-on-exec 属性，启动子任务后恢复，用已核验的 stdio receiver 传递 pipe 和重定向。客体验收使用现有串口控制台。 |
| glob、身份和语言环境 | glibc 系统 glob 链接需要当前 SDK 未提供的 `__getlogin_r` 和 `__getpwnam_r`。使用 GNU Make 自带的 glob，保留基于明示 `HOME` 的当前用户路径，账户查询分支留待相应系统能力。构建关闭译文目录、Guile 和动态载入，客体验收用 C locale。 |
| 信号与临时文件 | SDK 链接器仍报告 `signal`、`kill`、`alarm`、`umask` 及临时文件相关符号的缺口。递归 jobserver 和输出同步显式拒绝。并行通过使用正常退出与同步等待。 |

首次选择系统 glob 的真实链接失败记录保留在证据目录。运行输出同步负例时，
初次实现先触发临时文件缺口。现将拒绝放在统一的参数解码中，命令行和
MAKEFLAGS 均在启动输出同步前得到明确诊断。
[系统 glob 链接错误](../reports/gnu_make_glibc_20261126/initial_system_glob_link_errors.txt)
[初次输出同步负例](../reports/gnu_make_glibc_20261126/initial_output_sync_rejection.json)

公开的初次负例回执省略客体临时文件名，来源摘要记录在证据清单。组件登记绑定
已验签源包中的原 GPLv3 文本。二进制发行资格另行验收。
[证据清单](../reports/gnu_make_glibc_20261126/manifest.json) · [组件登记](../../licenses/components.json)

## 客体证据

在断网 Linux arm64 环境使用签名 glibc C/C++ kit 构建 GNU Make、dash 和
测试 ELF。在锁定的 QEMU 11.1.2 启动系统 `53424ae8acaebc44`，核对系统
镜像、GNU Make/dash/测试 ELF、SDK/profile 和 1,841 个系统源文件摘要。
[构建输入与摘要](../reports/gnu_make_glibc_20261126/build_inputs.json)

实际通过 11 项。Xsh 启动 GNU Make 并核对版本和目标标识。Makefile 读取
include，命令行覆盖变量，菱形依赖共享任务只执行一次，通配符匹配 FAT
目录中的 `vars.mk`。两个 `-j2` 子任务各自写入标志并等待对方，两个均
成功后才输出完成。recipe 管道和 `$(shell)` 捕获均检查实际传输字节。
并行失败时 Make 退出 2，独立目标继续，`.DELETE_ON_ERROR` 清理未完成
文件。随后经 dash 入口再次运行成功。递归 jobserver 和输出同步均被
明确拒绝，输出同步负例未触及临时文件。各项退出后保持 129709 空闲页、
3 个任务、1 个完成记录。
[客体回执](../reports/gnu_make_glibc_20261126/guest_report.json)
[串口日志](../reports/gnu_make_glibc_20261126/gnu_make.serial.log.gz)
[可重跑客体入口](../../tests/gnu_make_guest.py)

该资格覆盖串口和显式重建下的单 GNU Make 实例。增量时间戳、异步信号、
大规模并发和存量编译项目仍待组合验证。
