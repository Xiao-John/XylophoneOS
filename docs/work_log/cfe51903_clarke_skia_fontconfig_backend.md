# cfe51903 · ClarkE Skia 原生字体后端

在 #301 的 Fontconfig 基础上交叉编译 WebCore 使用的上游 Skia Fontconfig 字体管理器。
构建器校验 WebKit、栅格、Fontconfig、FreeType、LibXml2 归档和两份 SDK 的实际输入。
第一轮只替换 libc 时，旧终端归档缺少新 libc 引用的两个 fork 钩子，链接失败。随后
使用同份 C SDK 的头、CRT、libc、libm、终端支持和链接脚本，保留冻结的 Skia C++
头、libstdc++、libsupc++ 和 unwind 归档。输出包含目标后端归档和真实 C++ ELF。

未修补的后端在同一 FAT 输入已完成 Fontconfig 枚举之后，字体匹配退出 6。该路径
用仅支持文件映射的 `SkData::MakeFromFileName` 检查可读性。XOS 改用字形装载器
已有的 `SkStream::MakeFromFile`，由实际文件服务完成读取与短读补齐。原有系统字体
和应用字体选择、访问权限检查、sysroot 查找顺序和 FreeType 检查仍由已有后端处理。

基于 `aa267bfe` 合成 `c94f6bfe` 并重建普通镜像 `71365bb8c2e9691c`。真实 QEMU
由 xsh 启动，同一字体同时命中 `sans-serif` 与希腊语回退，绘制 U+03BB 得到字形
848 和 107 个非白像素。拒绝不覆盖的码点，空目录退出 5。原 Fontconfig 正负回归也
通过，两组均恢复 129696 空闲页、3 个任务和 1 个完成记录。普通 smoke 的 79 项、
10 项许可材料与 ABI 对照通过。
[源码、工件与客体回执](../reports/clarke_skia_fontconfig_20261127/manifest.json)

完整 WebCore 仍需绑定统一 C/C++ SDK，并验收字体缓存、整页布局、软件绘制和 Qt 视口。
[构建入口](../../src/ports/webkit/raster/README.md)
