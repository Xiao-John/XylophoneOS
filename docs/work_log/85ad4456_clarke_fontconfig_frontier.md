# 85ad4456 · ClarkE 的原生 Fontconfig 前置

Fontconfig 2.16.0 的发布归档与上游 SHA-256 一致。Linux arm64 环境以原 WebKit
SDK 和真实 FreeType、LibXml2 目标归档编译出了 x86-64 静态 `libfontconfig.a`。
启用该版上游头后，WebCore `FontCacheSkia.cpp` 及 `SkiaSystemFallbackFontCache.cpp`
均编译成目标对象。此前这两条线缺少目标 Fontconfig 头文件。

旧 SDK 链接 Fontconfig 程序时，glibc `realpath` 引用的 `__faccessat` 未定义。
新的 libc 路径访问改动从正常文件会话实现这一入口，并使无链接的 XOS 文件系统能
为 `readlink` 返回可区分的存在、缺失和路径穿越结果。该运行库改动独立交付。
[目标对象与失败链接的绑定](../reports/clarke_fontconfig_frontier_20261126/manifest.json)

这份回执覆盖目标归档、两个 WebCore 字体对象和旧 SDK 的链接失败。Fontconfig 客体、
Skia 字体后端的最终链接、WebCore 软件页面与 Qt 视口继续逐项验收。
[可重放的 Fontconfig 构建与客体入口](../../src/ports/webkit/fontconfig/README.md)
