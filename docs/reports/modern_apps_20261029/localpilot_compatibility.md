# LocalPilot 兼容性报告：第一阶段

2026-10-29。相同源码的Agent Core/API 1.0在XOS运行 **BLOCKED**；服务入口与实际前端依赖探针存在真实失败。
没有移植成功声明，没有运行Mac DMG，没有第二套Agent Runtime，也没有调整身份、Operator审批或Egress策略。

## 当前源码与拆分

已fetch私有 main `9a21ebbe6621de43be6568b64433230c317eb81a`（含QQ/微信渠道合并），
独立detached只读源码快照；原有工作区未改。[审计回执](localpilot_audit.json)保存版本、清单SHA、Python文件SHA、
逐行import及实际前端产物SHA，不导出私有源码正文。

| 部件 | 实际依赖/边界 | 本轮结果 |
|---|---|---|
| Python Agent Core | agent/localpilot_service/localpilot_api，Python>=3.10；HTTP/SSE/API 1.0、持久runtime、线程/进程/文件/网络 | 主机纯Python wheel构建PASSED；XOS原始服务导入FAILED。wheel的py3-none-any不是OS可用性证明 |
| Suite | Python>=3.11，协调Core/Companion生命周期 | 源码审计；完整客体生命周期NOT_RUN |
| Companion | Python>=3.11；watchdog、psutil、pypdf；MLX为optional | 原有独立生命周期保留；客体完整运行NOT_RUN |
| React/TypeScript | React19.2、Vite7、TS5.9；Tauri API、DOM、fetch/stream等 | 原始前端`npm ci --ignore-scripts`及`tsc -b && vite build` PASSED（HOST）；客体模块执行由最终回执记录 |
| Tauri/Rust宿主 | Tauri2、tokio、reqwest/rustls、tray、rfd、objc/AppKit | 已安装Rust1.96无XOS目标；完整target/std/WebView构建NOT_RUN |
| Node渠道桥接 | 原QQ/微信Node桥接，独立配置/鉴权/回执 | Node/libuv与网络底座缺失；桥接运行NOT_RUN |
| Apple桌宠/Computer Use | Swift AppKit、Accessibility/AX、ScreenCaptureKit相关捕获和原生效果 | XOS平台专项，NOT_RUN；不能空实现后声称兼容 |

版本依赖应以源SHA内清单及审计回执为准。MLX不列为首期必须项；显式配置远端推理仍受HTTPS与原云端Egress审批约束。
本轮没有连接推理服务或使用真实凭据。

## 逐项实际探针

新建XOS CPython3.14.9线程候选，接入已有SQLite3.54.1 XOS VFS及zlib1.3.2。
内核、libc、Python端口公共实现均未修改；是按已有端口从固定源码重新构建的独立候选。
完整命令/SDK/ELF/镜像/串口见[证据入口](README.md)。

| 项目 | 本轮观察 | 结论的严格范围 |
|---|---|---|
| Python线程 | PASSED：两真实线程join，锁内2000次追加 | 不是完整LocalPilot并发/故障资格 |
| SQLite | PASSED：磁盘建表/提交/关闭重开/完整性 | 本轮没有WAL、多进程并发或断电；重启持久性另验 |
| defusedxml0.7.1 | PASSED：有效XML解析，实体展开被拒绝 | 安全XML窄探针；没有关闭防护 |
| pypdf6.1.1 | FAILED：原包导入路径遇到缺失`_posixsubprocess` | 不是PDF解析结果；没删原包导入以制造通过 |
| psutil7.1.3 | FAILED：原包先遇到`_socket`缺失；原生POSIX进程单元编译也失败于getpriority/PRIO_PROCESS | 后续还有无XOS平台分支的源码缺口；不伪造PID创建时间或进程所有权 |
| Pillow11.3.0 | 原生`_imaging.c`单翻译单元编译PASSED；客体import FAILED：未静态集成`_imaging` | 原生链接、编解码、动态扩展装载NOT_RUN；不能称Pillow本身无法移植 |
| subprocess | FAILED：`_posixsubprocess`缺失 | 本轮没有fork/exec/stdio超时或取消的成功证据 |
| socket/HTTP | FAILED：`_socket`缺失 | 没有loopback监听、真实HTTP/SSE或API 1.0成功证据 |
| SSL | FAILED：`_ssl`缺失 | 没有HTTPS；保留默认链/主机名校验，未创建insecure context |
| 文件权限 | FAILED：原O_NOFOLLOW/owner-only打开被拒绝EINVAL | 没降级到普通open、没将合成stat模式当真实安全权限 |
| 随机数 | PASSED：32字节os.urandom | 不是TLS DRBG或长期熵资格 |
| 原Core模块 | FAILED：agent权限/策略、service security/server缺select，CLI缺fcntl | 包import会先执行其原始依赖链；不是逐个函数已经运行 |

[精确调用矩阵](localpilot_matrix.csv)绑定11个私有源调用点及原行号；[原生编译回执](README.md)保留正确构建宏补齐前后的失败。
任何“PASSED”仅指表中行为，不提升为Core或桌面版兼容。

## 安全与原样源码目标

先完成原API所需socket/select/线程/进程语义及可信文件元数据，再在原入口运行相同Core源码。
尤其`security.private_json`与workspace grants依赖O_NOFOLLOW、UID/mode、dirfd/文件身份稳定性，
不能以FAT合成权限或关闭检查获得“兼容”。保留审批主体、scope、Operator、任务收据、UNKNOWN、
撤销和云端Egress边界；若XOS服务不能满足，应拒绝启动相关功能并记录BLOCKED。

React源码保留。未来在真正Web引擎内运行原bundle，通过受控平台桥接接入同一Core API；
审计浏览器来源、令牌存储、SSE断线/重连、审批一致性、取消和UNKNOWN，不能创建另一个运行时接管状态。
本轮在独立JS解释器执行真实bundle只用于证明环境缺口，不替代目标WebView验收。

Tauri2需独立完成Rust target/std、WebView runtime、窗口/事件循环、输入、文件对话框及托盘后端；
当前x86_64-unknown-none不是带std的XOS用户态目标。AppKit、Swift Accessibility、ScreenCaptureKit、
NSGlassEffectView只能由明确的XOS平台实现替代，不能返回空成功。Mac arm64 DMG不是XOS ELF。

下一轮可在N2/HTTPS接口冻结之外并行：Python静态扩展候选、文件身份/权限设计、受控subprocess设计、
原API契约测试整理。完整服务验收仍必须串联真实客体HTTP/SSE和原安全回归。
