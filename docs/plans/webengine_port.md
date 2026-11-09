# XOS WebKit 浏览器底座移植计划

2026-10-31 · 状态：选型与终态架构经用户确认（2026-10-31）。本文只承诺验收门与裁决，
不承诺日期，不预填未测数字。落实 [C31](../xos_plan.md)：建设基础，而非制造已经完成的假象。

## 1. 目标与非目标

目标：

- XOS 拥有**自有浏览器底座**：真实 Web 引擎（HTML/CSS/JavaScript/DOM 全栈）、
  WebKit2 多进程结构、客体内可打开真实 HTTPS 网站。
- **长期可维护**：固定上游源、显式补丁记录、可跟随上游升级，不产生隐式分叉。
- 与微内核宪法同构：内容进程无特权，网络经用户态服务与设备授权，
  内核不为浏览器新增业务面。

非目标（各自另行立项，不借本计划预支）：

- React/TypeScript 与游戏栈：这些是本底座的**消费者**，本计划不交付任何应用框架。
- 音视频媒体管线（GStreamer 等）：后续独立评估、许可与登记。
- 100% 互联网兼容承诺：兼容面按 M5 实测报告登记，不预先声明。

## 2. 选型裁决：WebKit

| 维度 | Chromium | Gecko | WebKit（选定） |
|---|---|---|---|
| 语言/构建 | C++，**官方工具链强制 clang**（GCC 非支持路径），gn+ninja，Rust 占比上升 | Rust 占比高（Stylo、WebRender），需先为自定义目标移植 Rust std | C++20 + CMake；GCC 是官方支持编译器之一（webkitgtk 系发行版即 GCC 构建）；XOS 侧 GCC 16.2.0/CMake 已在 Qt 端验证【已验证】 |
| 结构亲和 | content 多进程可对上微内核，但工具链方向与 C06 相反 | 最差：Rust std 移植是硬前置 | WebKit2 的 UIProcess/WebProcess/NetworkProcess **就是用户态服务 + IPC**；WebProcess 作为无特权用户任务直接落在 C22/C28 授权模型上 |
| 沙箱 | 绑 Linux seccomp/namespace，需整体重写 | 绑 GPU/主流 OS 假设 | 授权与撤销用 XOS 自身机制（C22），无 Linux 沙箱依赖 |
| 自定义平台先例 | Fuchsia 端（但自带 POSIX/动态加载/套接字） | 主流 OS 之外几乎无先例 | Sony PlayStation 端、WPE、EFL 端：非主流平台 + 自定义显示后端的完整先例【上游公开资料】 |
| 关键配置自由度 | — | — | JSC 提供官方解释器-only 配置（`ENABLE_JIT=0`）；cairo 软件渲染为 GTK/WPE 端官方后端 |
| 许可 | BSD 系 | MPL | LGPLv2.1/BSD 双层；静态链接义务按 C10 第三方声明流程满足 |

- 淘汰 Chromium：clang 强制与 C06 GCC/G++ 主线直接冲突，沙箱绑 Linux。
- 淘汰 Gecko：Stylo/WebRender 要求先做 Rust 目标移植，等于加一个平台项目。
- 不走 QtWebEngine：它就是 Chromium，绕道承担同一冲突，另加一层构建面。

候选上游基线：`wpewebkit-2.54.2`（commit `32717fabcb9dcad9aa00a54ef1f23e41ee64e849`，
2026-10-31 经 GitHub tags API 核实）。正式源锁在 M0 完成并回填本文；
源锁完成前本文不声明任何源码哈希。

端口路线（M0 裁决项，凭真实交叉构建证据，不凭偏好预选）：

- (a) WPE embedder API 为基：嵌入面成熟，代价是 GLib 系依赖整体移植。
- (b) PlayStation 风格自定义端：无 GLib，平台层自写，代价是平台层工作量。

## 3. 终态架构（各里程碑是它的纵切片，不是临时版）

```
┌─ 客户机(QEMU) ─────────────────────────────────────────────┐
│ 浏览器 UI 任务（Qt/Aurora 壳，自有 chrome 与标签/书签等）      │
│   └─ WebKit UIProcess                                      │
│        ├─ IPC ─ WebProcess 任务（WebCore + JSC 解释器,       │
│        │           静态ELF，零设备特权，按C22/C28可撤销）      │
│        └─ IPC ─ NetworkProcess 任务（资源调度、缓存、          │
│                    HTTP 后端（M0 核实选型）                    │
│                     └─ IPC ─ 网络用户服务（TCP/TLS/证书）      │
│                              └─ 设备授权 ─ VirtIO-net        │
│ 内核（C28 不加面）：IRQ递送/应答、授权MMIO、DMA授予、IPC、撤销  │
└────────────────────────────────────────────────────────────┘
```

- 目标是隔离 UIProcess、WebProcess、NetworkProcess；实际入口、静态 ELF 组织和上游启动假设由 M0 验证，不预认上游构建形态。
- 网络策略、连接/会话身份在用户服务（与[引擎评估结论](aurora_browser_engine_evaluation.md)一致）；
  内核不解析任何网络协议。
- WebProcess 崩溃：客户端观察失败或结果未知，不伪造成功（C25）。

## 4. 无贷款裁决表（C31 落实）

| 表面像捷径的选择 | 为何是终态而非债务 |
|---|---|
| JSC 解释器-only（`ENABLE_JIT=0`） | 上游官方配置。未来 JIT 是**增量**：届时按 C20 论证内核新增 W^X 可执行页授权并先登记 ABI，不返工。 |
| cairo 软件渲染 → QImage/QPA 合成 | GTK/WPE 端同款官方路径；GPU 合成留给未来图形授权的自然延伸，不向内核加应用专属面。 |
| 静态链接、每进程一个 ELF | XOS 无动态加载器是既定架构事实，不是绕行；与 WebKit2 进程形态原生匹配。 |
| HTTP 栈从用户态服务起步 | [browser_http README](../../src/ports/browser_http/README.md) 的受限解析器和 obligations 是纵切片资产；完整网络后端及其需求按锁定版本审计。 |
| Qt/Aurora 作嵌入壳 | embedder 关系是上游常态；壳可替换，引擎不为壳打私有补丁。 |
| 上游补丁 | 一律进入 `source_lock.json`（补丁哈希显式记录），无隐式分叉；升级时补丁可审可重放。 |
| liteHTML 浏览器 | 其契约与冻结证据原样保留，本地页验收作 M2 对照子集；正式替代/退役另行登记，不悄悄改写旧证据（C18/C26）。 |

## 5. 里程碑与验收门

| # | 范围 | 验收门 | 性质 |
|---|---|---|---|
| M0 | 正式源锁；按 [posix_subset 契约](../contracts/posix_subset.md) 的状态词审计 WebKit 所需 POSIX 面（mmap/mprotect/生成/信号/线程/文件）；客机内存定容；(a)/(b) 端口路线用真实构建裁决；许可预演 | `docs/reports/webengine_m0_*/README.md` 落盘：未知全部变成有数的清单；本文回填确切源锁与 M3 重估 | 测量型 |
| M1 | JSC（`ENABLE_JIT=0`）+ WTF 静态构建在 XOS 运行；ES262 用 test262 出**实测**通过率 | 客体 guest gate 命令 + 通过率报告（只报数字，不声明完整兼容） | 机械型 |
| M2 | WebCore 本地页：ICU/freetype/harfbuzz/woff2/sqlite/libjpeg/libpng/libwebp/cairo 各自源锁与移植；Qt 壳嵌入视口渲染本地 HTML/CSS/DOM | [aurora_browser 契约](../contracts/aurora_browser.md) 的本地页/输入/像素/错误/回收用例作为对照子集通过 + 报告 | 机械型 |
| M3 | 网络用户服务：设备授权按 [network_device_v1 提案](../contracts/network_device_v1_proposal.md) 走独立登记 PR（C20 审核后实现，不复用旧 `sys_net_device` 帧代理）；lwIP 或等价 TCP 进用户服务；以受控 HTTP 纵切片验证网络；WebKit 网络后端按 M0 的上游接口与依赖审计选型；TLS/证书/时间/熵复用 CPython 已交付成果，TLS 库另行许可与安全评审；对接 NetworkProcess 后端 | 客体内对受控 HTTP/TLS 服务真实 GET；负向输入、超时、对端死亡用例；冻结回执 | 最长的杆 |
| M4 | WebKit2 三进程经 XOS 生成机制与 IPC 接通；WebProcess 零设备特权；进程死亡客户端可观察 | 页面在 WebProcess 渲染；杀进程后客户端报错不假成功（C25） | 结构型 |
| M5 | 真实 HTTPS 网站资格；恶意输入/资源耗尽负向验收；渲染器准入审计（引擎评估文档要求项） | pass/partial/fail/not_run 分栏报告，不预支完整兼容 | 资格型 |

量级说明：M0 后才能给 M3 实数；在此之前不给单一总数。已验证的地基
（GCC 16.2.0、newlib 4.6.0、线程 SDK 真 pthreads、Qt 6.8.3/QPA、CPython 熵与时钟）
使 这些地基不能证明 WebKit 的组合需求已经满足。M1/M2 的运行时、内存、构建、嵌入及多进程路径均为待测风险，网络也是独立关键路径。

## 6. 宪法与契约依赖

| 条款 | 本计划落点 |
|---|---|
| C06 | GCC/G++ 主线是选型核心理由；Chromium 的 clang 强制即淘汰理由 |
| C09 | 移植成熟引擎，不为原创性重写浏览器 |
| C10 | 每个上游依赖独立 source_lock（哈希/补丁/许可），发行保留声明 |
| C13 | Qt 为 GUI 主线：壳与嵌入面 |
| C19 | 本计划与各里程碑均走分支 + PR |
| C20 | M3 设备授权、未来 JIT 可执行页授权：先论证后入核 |
| C21/C28 | 网络策略、服务协议、设备驱动全在用户态；内核机制面不因浏览器扩大 |
| C25 | M4 进程死亡语义：观察失败，不伪造成功 |
| C29 | 网络 deadline/超时用统一时间机制，不私设时基 |
| C31 | 第 4 节无贷款裁决表 |
| C26 | liteHTML 浏览器的过渡处置按登记走，不作为新例外 |

## 7. 现有资产归宿

| 资产 | 归宿 |
|---|---|
| `src/ports/aurora_browser`（liteHTML 0.9，JS off） | 对照原型与 M2 子集验收来源；契约与冻结报告不改绑 |
| `src/ports/browser_http` 解析器 + 冻结回执 | 受控 HTTP 纵切片及测试资产；不预设为 WebKit 的完整网络后端，也不视其 obligations 为完整浏览器需求 |
| Qt 6.8.3 / QPA / display ABI | 浏览器壳与嵌入视口 |
| 线程 SDK（真 pthreads） | M1 起全部引擎线程 |
| CPython 熵/时钟/时区成果 | M3 TLS 与证书时间检查 |
| [posix_subset 契约](../contracts/posix_subset.md) | M0 审计的状态词与登记入口 |
| [network_device_v1 提案](../contracts/network_device_v1_proposal.md) | M3 前置：独立登记 PR 后才实现 |

## 8. 协调、风险与诚实清单

- 协调：user spawn / pio_grant 等在途工作线（文件范围不重叠）；`build/` 为共享目录，
  不并发构建；本计划组只碰文档。
- 已知未知（M0 前不给实数）：M3 网络工作量；静态全栈链接 WebKit2 的上游构建假设；
  客机内存预算；(a)/(b) 端口路线取舍。
- 本组**未做**：未编译任何 WebKit 代码、未跑任何新客体测试、XOS 网络能力零变化——
  计划落档不等于实现（C31）。

## 9. 计划修订：证据门与执行顺序（2026-11-08）

本节细化上述里程碑，不改变 WebKit 全栈、多进程、真实 HTTPS、用户态网络和
设备驱动的目标。上文中关于上游后端、许可、进程二进制形态与解释器配置的描述
为候选假设；须针对 M0 锁定的源码和实际配置核实，不能作为已通过的 XOS 证据。

### M0：可复现的路线裁决

- 锁定候选来源、版本、哈希、构建选项及补丁，记录每项第三方组件的来源、许可和
  静态分发义务。安全维护及上游升级策略在确定版本时一并审查。
- WPE 与自定义平台两条路线使用同一来源和工具链，分别记录构建命令、依赖闭包、
  实际到达阶段、阻塞项、运行时与 IPC 假设、预期补丁及维护面、许可和资源风险。
  一次仅遇到首个缺失头文件的尝试不足以裁决；证据不足时保留未裁决并列出下一探针。
- 按现有 POSIX 契约状态词逐项比对匿名/文件映射及保护、进程生成、线程、信号、
  文件、等待、socket、事件循环和共享数据；记录所需语义、所有者、现状及客体验据。
  不因 Qt 或 pthread 的既有测试通过就推定 WebKit 组合需求成立。
- 对启动、多进程常驻内存、峰值和资源上限制定可测 profile；M0 未测项标记未测，
  不预设在现有配额内可行。结束时记录路线裁决或阻塞原因、可重现报告和下一步。

### 先验证结构，再接入真实引擎

M0 后增加独立结构探针：在 XOS 客体验证进程启动、双向 IPC、帧缓冲传输与所有权、
输入路由、对端故障和退出回收，记录复制与共享方案的权限和资源代价。探针不是
WebKit 运行证据。M2 在实现前声明真实 WebCore 的进程位置和视口接入方式，并在同一
客体测试本地页面、输入、像素、故障与回收；M4 再证明真实 WebKit2 进程分离、
授权、进程死亡和恢复边界。任何阶段不可把探针或宿主构建冒充目标机通过。

### M3：可独立交付的网络链

依次验收设备授权与撤销、用户态驱动收发、IP/TCP、DNS、受控 HTTP、TLS 与
证书/时间/熵，最后接入选定 WebKit NetworkProcess；互不依赖的引擎工作可并行。
每段同时记录故障、超时、取消、资源与对端死亡结果；端到端验收绑定真实客体、
受控服务、挑战和响应字节。browser_http 的受限 Content-Length/GET 解析器可供
纵切片和测试使用，但不支持 chunked、压缩或 HTTPS，不能预先视为完整浏览器网络栈。
网络后端由锁定版本的实际接口、成熟组件和维护成本裁决，不以解析器替代网络服务。

### 安全与 M5 验收

进程数量不等于隔离。明确 WebProcess 对文件、网络、显示、进程与 IPC 的实际授权、
来源及撤销；验证跨来源访问、过期句柄、进程/服务故障和资源耗尽。TLS 负向用例
覆盖主机名、证书链与过期、不可信时间、熵不可用及禁止降级；不可绕过校验取得通过。

M5 固定版本化的受控站点和测试配置，分别测加载、脚本、字体、输入、导航、存储、
进程隔离与资源；外部真实网站单列访问时间、版本和结果。测试集的版本、覆盖及
pass/partial/fail/not_run 均须报告；受控站点通过不代表互联网兼容，单次打开网站也
不替代可重现测试。保留 liteHTML 原始契约和冻结证据，不重新绑定历史结果。

## 10. 下一步（可直接执行）

1. M0 第一步：按 `src/ports/aurora_browser/source_lock.json` 的 `git archive` + sha256
   先例对候选基线做正式源锁，落 `src/ports/webkit/source_lock.json`；命令序列与哈希
   写入 M0 报告并回填本文第 2 节。
2. M0 第二步：以 posix_subset 契约状态词出 POSIX 缺口清单。
3. M0 第三步：(a)/(b) 各做一次真实交叉构建尝试，凭报告裁决端口路线。
