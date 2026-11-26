# aff51323 · dash 静态 glibc 预览

以 `bac10c6d` 为基线，通过现有 `scripts/build_dash.py` 增加显式 `--glibc-profile`
入口。目标仍为原来锁定的 dash 0.5.13.5，归档 SHA-256 为
`40090101a2a491f13e901d3d48e90414f26634628b9bfff35ff540363c227a7d`。
候选资格、完整 SDK 与 GCC/G++、汇编器、链接器的摘要经验证后进入独立预览缓存。
选用候选 SDK 的标头、CRT 和归档。只有控制台桥接单元使用 XOS 原生标头和系统调用
源文件。编译后的 ELF 保留映射在首段的 ELF 头及完整字节。常用入口见
[dash 端口说明](../../src/ports/dash/README.md#static-glibc-preview)。

## 从原入口到目标 ELF

| 环节 | 实测结果 |
| --- | --- |
| 原入口直接传入候选 sysroot | 控制台桥接找不到 `xos/process_abi.hpp`，原入口使用 newlib SDK 布局。首份日志摘要 `547998ad785d24bf434247897ea6d8f7e9b2a33ebf33114b866b610151c1fc33`。 |
| 独立预处理验证 | 追踪确认全量 `src/user/include` 使 newlib 风格的 `dirent.h` 先于 glibc 标头。缩小原生标头范围后使用实际 glibc `dirent.h`。证据 `cb8a3ed54ce32af2cc892390c664c70a073c1952d215f02d5f95e6b143a2f0af`。 |
| 使用 glibc CRT 与库的全 C3 目标 | 目标源可编译。链接缺少 `xos_open_anonymous` 和 `xos_seal_anonymous`。`fork`、`execve`、`__spawni`、`pipe`、`access`、`chdir`、`getcwd` 同时报告 stub。日志摘要 `d1a293bf0ae8bee2a328c1cbf858fa751335d7a5d824e1860848b7021f8c5044`。 |
| 有限脚本 profile | 在 dash 的语法准入与执行入口明确拒绝依赖缺失机制的操作。完成独立静态链接。 |

采用已签名验证并重建分配器锁的 C SDK。SDK manifest 为
`cc77585fd4f30399b1a635091e3ec66c9a4f5731610d94000094bba99eee7a28`。
GCC/G++ 16.2.0，GNU Binutils 2.47.20260726。将环境中的 `CPATH`、
`CPLUS_INCLUDE_PATH`、`LIBRARY_PATH` 显式指向旧 SDK 后执行 glibc 分支，实际构建
使用清理后的环境。目标 ELF SHA-256 为
`271ae46051bdcf1a7e3ed77fb88a55cadbd9050f06809de3c6aeeff9bf140646`，回执为
`c76ac60fdddbd63d8746ad19dec3364b197c8c07129b998a047edb23e8e60747`。

## 客体结果

Linux arm64 宿主、QEMU 11.1.3、x86_64 BIOS 客体。由本次源码重建的系统为
`a4886212360281da`，ISO 摘要为
`814a5676409256395461f6dee9fd7e34e8d5d8d6e577abfd15782b58cbbbdbd9`。
[双入口门禁](../../tests/dash_glibc_preview_guest.py) 绑定系统、SDK、源码及产物，在独立
FAT 工作盘通过 xsh `exec-file` 和现行 newlib dash 外部命令启动预览。该盘安装了常规
`/usr/bin/dash`，预览版导入 `/bin/dash_glibc`。

| 场景 | xsh | dash |
| --- | --- | --- |
| 函数、`case`、参数扩展及 builtins | 退出 0 | 退出 0 |
| 文件重定向、读取、dot 脚本 | 退出 0 | 退出 0 |
| 管道、子 shell、命令替换、here-document | 各退出 2 | 各退出 2 |
| 执行外部 ELF | 退出 126 | 退出 126 |

14 项均检查输出和资源恢复 `[129700, 3, 1]`，关机后回读了预览 shell 写入的文件。
`getcwd` 的启动诊断保留。首次测试把外部命令的预期诊断写为 libc 字符串，实际为
`external commands unavailable in the glibc dash preview`，退出 126。修正匹配后同一
字节的 ELF 完成双入口测试。原始与最终日志保存在本工作区 `build/dash_glibc_proof/`，
最终报告 `20490b4ad0c435ed0403ff2f22300645eab98d59a260e98203d87cc42206d3d6`，
串口 `4d70bcfc3fd8a178a1d1ce2aaf5fce9432dce6b6d063314a2c76ab4515382607`。

使用同一系统的 newlib SDK 重建常规 `dash_c3`，ELF 与先前结果逐字节一致，摘要
`94be9cc12698f6da03be0737e938f0c3d1f42061c3f89f3bcec869fcfc191067`。
先构建常规版再构建预览版，普通安装 ISO 仍装入上述常规版。安装回执摘要为
`8edd8881486b6a199c33fbb99a9f8f7d07efd45372e359bc8327cd1af906bb0f`。
预览 SDK 与另一份 C++ SDK 的 profile 配对时被拒绝。
`tests/dash_pipeline_fds_test.py` 通过。glibc 交互终端、完整 C3、应用包安装及默认
切换仍各自待验。
