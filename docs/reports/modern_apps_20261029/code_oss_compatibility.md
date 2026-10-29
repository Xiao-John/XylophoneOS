# Code - OSS 兼容性报告：第一阶段

2026-10-29。Web工作台与Electron桌面版均 **BLOCKED**；没有Code - OSS移植成功声明。
本轮实际执行原上游扩展宿主脚本，得到真实客体失败；没有制作Monaco外观替代应用。

## 固定源码

Microsoft Code - OSS **1.106.0**，SHA `ac4cbdf48759c7d8c3eb91ffe6bb04316e263c57`。
其`.npmrc`指定Electron **37.7.0**；实际Electron DEPS指定Chromium **138.0.7204.251**、Node **v22.20.0**。
Electron/Node已解析到实际commit，见[源码锁](source_lock.json)。这与独立浏览器报告的Chromium142不是同一输入，
不能交叉借用资格。版本为固定审计样本，不是面向2026年的生产安全版本推荐。

没有完整Code/Electron checkout及node_modules，没有跑Code或Electron全量构建；这些均NOT_RUN。
实际构建/运行是：真实XOS SDK接口编译、QuickJS ELF构建/运行、实际上游HTML内script的客体求值，
以及Node/libuv/Code调用点审计。源码文件和每个失败都有SHA/命令/日志。

## Web工作台/Monaco

[code_oss_matrix.csv](code_oss_matrix.csv)是逐行实际调用点矩阵，共12项，含当前行为、缺口、建议负责者与探针。

| 能力 | 已核对的真实依赖 | 本轮状态 |
|---|---|---|
| 工作台/Monaco | DOM节点、textarea、CSS/layout、selection、输入/IME/clipboard/可访问性；NativeEditContext是其中一条实现路径，并非所有浏览器都必须有该API | BLOCKED；编辑/命令/文件操作NOT_RUN |
| JavaScript Worker | 扩展宿主iframe内创建Worker、MessageChannel/port和消息传递；模块资源加载 | BLOCKED；真实Worker启动/关闭NOT_RUN |
| 来源与隔离 | iframe sandbox、parentOrigin检查、URL/TextEncoder/crypto.subtle | 原扩展宿主iframe脚本FAILED于缺失URL；没有给宿主对象写假实现继续跑 |
| WASM | JS解释器无WebAssembly API；具体WASM消费者和模块闭包尚未穷举 | 能力查询为undefined；WASM运行NOT_RUN，不凭此声称所有Code功能都硬依赖WASM |
| 文件存取 | HtmlFileSystemProvider用浏览器文件句柄及IndexedDB；远端provider是另一条独立路线 | BLOCKED；需浏览器持久化/配额或受控原生文件桥接，不能跳过授权 |
| 扩展API | WebWorkerExtensionHost与RPC、扩展运行位置/资源/权限；Web扩展不等于Node扩展 | BLOCKED；安装/激活/命令/取消/错误恢复NOT_RUN |

实际上游`webWorkerExtensionHostIframe.html`按固定SHA取文件，仅提取原`<script>`内容，没有改其代码。
在真实XOS进程执行时返回`ReferenceError: 'URL' is not defined`，进程错误退出并回收。
它是环境前置失败，不是整个工作台已加载后失败。独立JS语言成功与浏览器DOM/Worker/WASM成功分别登记。
现有Aurora/liteHTML没有JavaScript，不能承载该工作台；QuickJS也未添加DOM，因此不是已可用Web引擎。

## Electron桌面版独立审计

| 面 | 真实调用/依赖 | XOS当前缺口与建议实现方 |
|---|---|---|
| Electron | 固定Chromium138+Node22、窗口/IPC/renderer/broker和原沙箱 | 引擎/GUI/安全共同设计原生平台；不加`--no-sandbox`或单进程替身宣布通过 |
| Node/libuv | `uv_spawn`、Node fs、epoll后端 | Node/进程/等待/文件负责人；线程profile fork/exec、事件循环和FD语义须逐项补齐 |
| PTY/终端 | Node tty wrapper调用uv_tty_init；Code pty service依赖node-pty的原生链 | PTY/控制终端/termios/resize/EOF/cancel及stdio所有权；SDK头编译FAILED，终端功能NOT_RUN |
| 文件监控 | libuv Linux分支inotify_init1，Code watcher管理 | XOS文件服务需要有界订阅、overflow/rescan、撤销与退出；不能轮询后冒称同等语义 |
| 语言服务器 | Node/native可执行子进程、stdio或socket、工作区文件 | 子进程/API/取消/资源预算；真实LSP初始化/诊断/退出NOT_RUN |
| 调试器 | Debug adapter进程、DAP通道及实际目标调试机制 | 进程/调试/安全负责人；DAP与内核调试机制不能混为一谈；NOT_RUN |
| Git | Git可执行程序、进程/管道/文件语义，远端还需SSH/TLS | 没有本轮Git构建或运行资格；diff/status/commit/remote分别验收 |
| 扩展宿主 | 真实Node进程、模块/原生扩展、RPC、信任/权利/故障恢复 | 生命周期/装载/权限机制缺口；不能把Web扩展成功推广到所有桌面扩展 |
| 资源 | XOS全局8进程、每进程4线程、全局32线程；单进程65536页的限制 | 需先量实际组件需求与最小可运行配置，设计受控配额；未测Code峰值，不先任意扩大限制 |

相关SDK编译前置探针socket/dlfcn/PTY/inotify均FAILED；它们是必需接口的窄探针，
不能冒称完整Electron/Node编译日志。Node/Electron/LSP/DAP/Git真正运行均NOT_RUN。

## 后续客体门槛

先让目标Web引擎证明DOM/CSS/事件、Worker/消息、模块资源、WASM、来源隔离及文件持久化，
再启动原Web工作台，逐项验编辑/保存/重开、命令、一个固定Web扩展及失败恢复。
Monaco单独运行只计编辑器探针。桌面版独立推进Rust/Node之外的Electron/XOS平台闭包，
以真实PTY、文件监控、一个LSP、一个DAP及本地Git操作作阶段门槛。

系统外框可沿用Aurora Glass；本轮不重写视觉库，也不把相似界面作为Code功能证据。
