# D1 · 当前主线的 GNU 重定位与共享 G3 组合

固定闭包进入独立的 #295。本组合树复用此前实际验收的 GNU 重定位、XOS
启动参数及文件交接。重放时保留现有独立堆期限和零固定依赖用例，并让新增
GNU 夹具继续校验冻结编译输入。当前 `dl-sysdep.c` 守卫继续生效。

在主线 `d7c56292` 的组合树 `2dd2053b` 上重建验签 GNU glibc 2.44 C SDK
及正常系统 `da538afb7c13cd56`。真实双 DSO IE TLS 重定位、文件映射、
本地入口准备、GNU 启动状态、GNU callback、共享 G3 三路径都通过原生 QEMU。
入口准备还覆盖有效堆预算下的空固定依赖。原有分支和各自验收保留。

## 外部 C 使用共享 G3

GNU XOS 版本脚本把真正的 `__errno_location` 放入目标已有的 `GLIBC_2.44`
节点。共享组件继续使用 GNU 共享规则编译的 `read`、`close`、TLS errno 及
XOS G3。单独编译的 C 消费者通过正常 GNU ld 连接该组件，获得真实的
`DT_NEEDED`、`BIND_NOW` 和三个 `R_X86_64_JUMP_SLOT`。`read`、`close`
和 `__errno_location` 都要求同一个 `GLIBC_2.44` 节点。

原生启动保持消费对象和 G3 两个已验证文件 pin，运行 GNU 版本检查、重定位
和 RELRO。消费对象的三个 PLT 槽都指向实际共享组件。运行代码通过正常 C
头文件读取、关闭及访问 TLS errno，分别覆盖 v2 重定向 stdin、v3 本机 exec
的两个共享偏移别名及 CLOEXEC 清理。版本拒绝时旧文件会话仍可用，两个依赖
文件的写端都可重新打开。

从 `2db340dc` 重建签名 SDK 和正常 ISO `0a0da35dc7214edc` 后，这组三条
原生路径均通过，退出后恢复 `129696 / 3 / 1`。该外部 C ELF、真实共享组件
及观察器有独立源码和字节摘要。探针由原生静态入口启动，仍需完整原生 GNU
`ld.so`、`dl_main` 和 `libc.so` 的组合启动验收。

在 `bbf38ffb` 的组合树 `090c0010` 上再次从源码归档验签并重建 C SDK、GNU
对象和正常系统。QEMU 通过共享 G3 的三条路径、GNU 初始执行重定位、固定
闭包、初始 TP 和 GNU callback。解包三个归档并重跑共享 G3 后，SDK、原生
镜像、探针、父进程及三份 DSO 的摘要与首次验收相同。

| 验收输入 | SHA-256 |
| --- | --- |
| 正常原生 ISO `09545b1b6ad70f3c` | `28b70eeec593dd5bc55cac56166ae9dd1237dba7f4d5e01d50564e3d8979648f` |
| glibc C SDK 清单 | `973d91172d8958432edc60c325a3bb3973aaf2146e46916c78983634f941db25` |
| SDK profile | `812a7dddfd9941522e7689e9912294bef82fb4a25d7be9112153c9c89f175947` |
| GNU rtld 清单 | `907b41a7dd68917c320901537f4843ab6918722a6bf85badf063281fb34b166c` |
| 外部 C 消费者 ELF | `da3edc5845f82eff6587e5d2a710ae1e0a73c9c6819c6aa7653601458b40e804` |
| 原生探针 ELF | `106acdee56859909fd733d10332be4cc2183c16a481cba92341929196a2db9aa` |

本地 `build/shared-current/post296` 保存原始串口、绑定清单和可重放归档。
GNU 对象由 `scripts/probe_glibc_rtld.py --libc-handoff-fixture` 生成。用
`tests/glibc_d1_libc_handoff_guest.py` 绑定 `--system`、`--sdk-build`、
`--rtld-proof`、`--profile`、`--dash`、`--dash-receipt` 和新的 `--output`。

## 余下的启动边界

真实 GNU 共享 x86 内存函数依赖 `cacheinfo.os` 的 IFUNC 初始化及解译器
`_rtld_global_ro` CPU 状态。此共享 G3 组件使用验签源码内的 GNU 通用内存
函数。完整解释器须核对 GNU 自重定位、真实 libc 重定位与 CPU 初始化顺序，
再运行初始化、G3 所有权交接及现实 C 程序。#294 的静态
`spawn_verified_file` 可复用已验证的同字节快照，现有启动准入仍限定静态
ELF。D0 动态闭包身份、启动 ready 和公开入口门禁继续适用。
