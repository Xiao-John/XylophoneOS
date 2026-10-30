# Web平台接续：语言、装载与来源边界分别验收

2026-10-29。固定来源沿用PR #21，不更新为“最新版本”。
[源回执](source_audit.json)逐字节重核45份公开源码；这是文件子集，不是完整checkout。
Chromium `4b8153ab58d3c3f4c9f7e4baad9616ecf80db5fa`，V8
`bb294624702efbb17691b642333f06bf5108e600`，Code - OSS
`ac4cbdf48759c7d8c3eb91ffe6bb04316e263c57`，Electron
`dfc60f0f4246a542a45601f93572eca77bdff2f9`，Node
`caa20e28dc1f21a97f7b2a7134973fd6435b65f0`。

## 可执行探针与其证明范围

[runner](../../../../tests/modern2_runtime_guest.py)用真实XOS进程运行重新交叉构建的
QuickJS，不提供DOM/Web API替身。语言内存、Promise job、单个ES module与跨文件加载
分别测试；失败后再执行buffer脚本，检查Shell继续可用并逐次回到相同资源计数。
完整串口、命令、SDK/ELF/镜像/夹具哈希由回执单独绑定，旧PR21结果不重新绑定。

| 探针 | 实际操作 | 不得推导的能力 |
|---|---|---|
| buffers | ArrayBuffer/DataView字节序、TypedArray共享视图与slice复制 | V8的page allocator、JIT、W^X、共享进程内存 |
| promises | 排空后确认Promise fulfilled及结果值，pending/rejected/异步断言负控制真实失败 | I/O事件循环、线程调度、浏览器task/microtask完整规则 |
| module | 顶层await、export的单模块执行，排空后确认其Promise fulfilled；pending模块必须失败 | module graph、URL解析、fetch、CORS、缓存、循环加载 |
| import | 从真实文件路径import另一个真实模块 | 未配置宿主module loader时的失败只说明该embedding缺口，不说明QuickJS语言不支持ES模块 |
| DOM / events | 直接createElement与EventTarget调用 | liteHTML本身不是DOM/事件实现 |
| Worker / WASM | 直接Worker构造与最小WASM module校验 | Promise和TypedArray不证明Worker、WASM或浏览器沙箱 |
| origin | location.origin访问及全局能力清单 | 独立解释器无URL来源模型，不得用常量true伪造crossOriginIsolated |

## 来自原Code源码的具体前置

在固定`webWorkerExtensionHostIframe.html`，`:13`同时需要URL与document，
`:18`读取window.origin，`:79,145`核对message origin；`:111`创建Blob URL的module
Worker，`:120,148`转交MessagePort，`:94`只有真实crossOriginIsolated后才启用相应分支。
`webWorkerExtensionHost.ts:135–143`创建并配置sandbox iframe；`:186`发送bootstrap，
`:221`转交message ports。原来源检查和sandbox配置必须保留。
这些实际调用点形成下列分阶段gate，不能用六个同名JS对象替代。

| 方向 | 后续最小真实gate | 系统前置/归属 |
|---|---|---|
| V8平台 | XOS OS选择、页尺寸/地址预算、page allocator reserve/commit/protect/decommit/release；真实线程/锁/等待 | PX4-A认领及实施；线程预算、栈、退出回收；不定义Linux宏绕过OS选择 |
| DOM/事件 | document创建/节点变更/布局、真实输入事件、listener生命周期、页面销毁 | 引擎/图形层；不是内核HTML接口；复用受控显示/输入 |
| module加载 | 有相对URL/环依赖/失败恢复的module graph、来源绑定和重定向策略 | 用户态loader+真实网络；N2之前仅可设计文件scheme，不能冒称HTTP |
| Worker | 真独立执行域、MessageChannel顺序/转移、异常、terminate、资源回收 | 用户态引擎+受保护IPC/线程；跨来源与调用者身份验证 |
| WASM | 最小验证/执行、越界trap、内存grow失败、执行权限与错误恢复 | 独立WASM引擎配置与PX4-A；解释配置也需实际验证，不取消W^X/NX或sandbox |
| 来源隔离 | 两不同来源的DOM/存储/网络权限隔离、伪origin消息拒绝、iframe sandbox、正确COOP/COEP与SAB门槛 | 用户态安全策略、进程/IPC边界、可信网络；不以共享全局对象模拟 |

Chromium完整构建、原生V8运行、Electron/Code工作台、通用WebView、安全浏览器沙箱、
HTTPS和正式发行均NOT_RUN。QuickJS仍只是实际语言运行证据。
PX4-B共享/文件映射与动态链接器分期推进，不能用本轮匿名VM提案预先承诺。
