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
