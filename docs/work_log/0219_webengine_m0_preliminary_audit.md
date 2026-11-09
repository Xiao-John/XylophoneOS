# 0217 WebKit M0 前期审计：本地基线

2026-11-08；工作树 HEAD `fdadfe77b93c878fa5b379193e11a8be0a07202e`，另有未提交的浏览器计划修订。此记录只审计本地 XOS 地基，不代表 M0 完成或路线选定。目标和验收门见 [计划](../plans/webengine_port.md)。

## 已观察到的事实

- 本工作树 `src/ports` 未见 WebKit 移植或正式源锁；候选 `wpewebkit-2.54.2` 及提交号来自计划，尚未在本次核验源码字节。局部文件搜索不能证明其他工作区或私有存储没有源码。
- 宿主 PATH 上 `cmake` 4.4.4、`ninja` 1.13.2、`x86_64-elf-g++` 16.2.0 可执行；版本存在不等于匹配 SDK、WebKit 可配置或交叉构建通过。`build_threading_sdk.py` 要求已验证的 newlib 前缀和 C++ 模式下的 GCC 源码与回执，本次未核验现成 SDK。
- `src/user/libc/newlib_syscalls.cpp` 的 `mmap` 与 `munmap` 返回 ENOSYS；[POSIX 子集契约](../contracts/posix_subset.md) 将映射标为 unsupported、共享映射和 `mprotect` 无资格。WebKit 的具体配置是否以及如何依赖它们仍须对照上游源码与构建结果。
- POSIX 文档记录单线程 fork/exec、FD、文件和 pthread 为各自有限范围的 accepted_subset；异步信号、socket 等不能据此视为完整。该文档自身是历史快照，具体调用必须核对当前实现和绑定版本的客体证据。
- `process_max_pages` 为 65536，是代码中的单进程页数上限，不是 WebKit 内存需求或可用内存测量；未测三进程、线程、栈、帧缓冲及峰值。
- 当前 [state](../state.md) 记录设备授权段 1a、N2 BLOCKED；`sys_device` 已登记不代表完整授权、DMA 隔离或网络可用。`browser_http` 的有限解析不构成 TCP/TLS 客体链路。
- 历史 [WebKit readiness](../reports/ssg_p3c_engine_neutral_20261031/webkit_readiness.md) 明确是要求清单，不是实际引擎或 SSG 集成。

## 待完成的上游对照与路线裁决

| 审计面 | WPE 路线 | 自定义平台路线 | 当前状态 |
|---|---|---|---|
| 固定源码、构建配置和许可证 | 待取样 | 同一源码待取样 | NOT_RUN |
| 构建工具、主机生成器及依赖闭包 | 待从源码和配置输出建立 | 同左 | NOT_RUN |
| POSIX、内存映射、线程和进程具体调用及替代语义 | 待提取并映射 XOS 证据 | 同左 | NOT_RUN |
| UI/Web/Network 进程启动、IPC 和显示嵌入 | 待验证实际接口 | 待验证实际接口 | NOT_RUN |
| 补丁数量、升级成本、静态分发义务 | 待审计 | 待审计 | NOT_RUN |
| 真实 XOS 交叉配置与构建阶段 | 未执行 | 未执行 | NOT_RUN |

不能凭此表选择路线；各项应包含命令、版本、原始结果、明确的首个阻塞及继续调查记录。不能用第一个配置错误推断整体不可移植。

## 执行记录与下一步

本次只读项目计划、契约和源码，查询宿主工具版本；未联网获取源码、未建立 source lock、未构建 WebKit、未运行客体测试、未进行许可闭合。M0 状态为 **in_progress，未验收**。

下一步在获准访问上游或拿到可信本地源码后，对候选来源及完整字节做正式锁定，核验依赖和许可，制作同源的两路线配置记录；随后将真实调用映射到 XOS 的实现与客体证据，并测量各进程资源。网络前置按独立设备授权与 N2 路线推进。不得将该前期审计解释成引擎、HTTPS 或多进程已实现。
