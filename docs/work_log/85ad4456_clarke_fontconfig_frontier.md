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

## 原生 FAT 字体查找

重建带路径修复的签名 glibc C SDK 后，同一版本 Fontconfig 已经链接为静态 XOS ELF。
普通镜像 `c85c7bc6f1c0a937` 实际执行它。程序先加载 XML 别名，确认 `sans-serif`
查询已替换首选家族，然后从 FAT 扫描 DejaVu Sans 并查验 `U+03BB` 的覆盖。空目录
返回预期退出码 5，两个过程均回到 129696 空闲页、3 个任务及 1 个完成记录。
系统源、SDK、FreeType、LibXml2 和客体输入分别绑定在回执中。
[FAT 字体客体回执](../reports/clarke_fontconfig_fat_20261126/manifest.json)

WebCore 两个字体对象的目标编译已有证据。它们与 Skia 字体管理器的组合链接、全页面
几何、软件绘制和 Qt 视口尚未验收。当前探针全程使用应用配置，缓存与全局字体配置
留给后续生产配置。
