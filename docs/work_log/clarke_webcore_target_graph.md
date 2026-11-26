# ClarkE 的静态 WebCore 软件构建目标

2026-11-27。锁定 WPE WebKit 2.54.2，沿用 XOS 的 JSCOnly 和静态 JSC 构建入口。
新选项 `XOS_WEBCORE_SOFTWARE` 在 CMake 生成同一个静态 `WebCore` 目标，启用 CPU
Skia，并接入 XOS 目标字形和格式归档。生成的目标包括 HTML 分词、DOM、CSS、
布局、图形上下文和 Skia 字体。软件配置选择的源表排除了加速缓冲区、纹理图集和
GPU 绘制引擎。原生网络声明保存值类型，实际请求仍需接入 XOS 网络服务。

软件缓冲区创建沿用上游 `ImageBufferSkiaUnacceleratedBackend`。序列化对象引用
软件缓冲区，在消费时移交同一缓冲区。其内存用量、所有权和跨线程转移沿用 WebCore
既有约束。XOS 页的滤镜模式只选择可用的实现。

从锁定归档重提相关文件应用补丁，13 个输出与参与配置或编译的文件逐字节相同。
Linux arm64 上的 CMake 4.4.5 生成 550 个 WebCore 编译单元，配置明确启用 Skia、
禁用 Skia 编码器、JIT 和 WebAssembly。配置绑定本轮统一 glibc C/C++ SDK 与 14 份
目标归档。两份独立缓冲区源用 GNU 16.2.0 通过交叉编译，x86-64 对象未引入 GL 或
加速后端符号。它们的编译回执与整个 CMake 图分别保存。

真实 `WebCore` 构建已进入目标依赖编译。首次尝试触发上游针对无优化 Release 的
编译拒绝，已改为 `-O1`。后续补齐全量目标编译、归档、DOM/CSS 客体和 Qt 视口，
再绑定最终 SDK 与完整依赖重建结果。此次配置仍使用已经验收的目标依赖归档。
[软件目标配置](../../src/ports/webkit/page/README.md#webcore-软件构建目标) ·
[配置和对象回执](../reports/clarke_webcore_target_graph_20261127/manifest.json)

## 目标命令复验

通过 CMake 的正常生成规则补齐 PAL、WebCore 和 JSC 头文件与绑定。`HTMLNames.cpp`
和包含 `HTMLDocumentParser.cpp` 的目标编译单元通过。首轮编译同时定位到 HarfBuzz
功能开关、未启用辅助功能时的对象包装，以及 XOS 共享内存类型缺失。

WebCore 目标现在启用已绑定的 HarfBuzz，并在未启用辅助功能时沿用上游的本地包装；
将 WebCore 默认合并编译批次减为 2 后，CMake 列出 2170 个 WebCore 编译单元。
生成的实际规则通过 `HTMLNames.cpp`、`GraphicsContextSkia.cpp` 和
`SkiaSerializedImageBuffer.cpp` 所在的三个目标单元。部分页面和布局单元的编译器
进程被信号终止，保留原始回执。复跑的构建统一采用较小批次，并显式允许无优化诊断
构建。原生共享内存接口与整页客体验收仍继续推进。

## 页面与布局对象

将 #322 的原生共享内存补丁叠加到同一份锁定源码后，重新生成目标图。Linux 容器中
编译了 `SharedMemoryXOS.cpp` 和实际 DOM 生成输入。其后又有 WebCore 编译器进程被
信号终止。保留容器的原日志，并移植 CMake 生成的命令路径与导出头链接供 macOS 上的
同版本 GNU 交叉工具使用。单独编译的 `Page.cpp`、`RenderView.cpp` 和
`HTMLDocumentParser.cpp` 均生成 x86-64 目标对象，检查了 `Page` 构造、`RenderView`
布局及绘制符号。组合对象回执单独绑定目标图、补丁、编译器和三个实际工件。完整归档、
最终链接和客体页面按各自的验收条件继续验证。
