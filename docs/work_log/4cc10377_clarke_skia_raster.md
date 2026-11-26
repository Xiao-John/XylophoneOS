# 4cc10377 · ClarkE 的目标 Skia 软件栅格

以 #283 合入后的 `1a840d43` 为基线。目标前置从锁定 WPE 2.54.2 归档编译
Skia 软件绘制源，从锁定 QtBase 6.8.3 编译 libpng 1.6.47 与 libjpeg-turbo
3.0.3，使用锁定 zlib 1.3.1 和此前验收的 FreeType 2.13.3。Qt 包保留 JPEG 的
8、12、16 位源变体。CMake 的库和头检查绑定目标产物。
[独立构建入口](../../src/ports/webkit/raster/README.md)

以同一 glibc C/C++ SDK 生成 520 个 Skia CPU 翻译单元，保留实际颜色、几何、
绘制和字体入口。构建去掉依赖 GPU 后端的源，补齐独立软件链接需要的上游
`SkStrikeRef.cpp` 并显式选择 POSIX semaphore 路径。字体管理器保留可注入字体
数据的上游实现。随前缀保存原始许可证成员和登记文本摘要，目标未纳入二进制发行。
[静态目标绑定](../reports/clarke_skia_raster_20261126/target.json)

从 `4cc10377` 重建普通 ISO `8acc1ba84d2434de`，用 QEMU 11.1.2 运行。同一原生
ELF 从 FAT 读回后核对输入摘要。Skia 生成实际 12×10 像素并逐点核对白背景、
裁剪蓝块、重叠红块和裁剪范围外的像素。程序返回 0，恢复 129696 空闲页、3 个任务和
1 条完成记录。普通系统的声明材料检查通过 10 项。
[栅格客体回执](../reports/clarke_skia_raster_20261126/manifest.json)

下一阶段将实际 DOM/CSS 布局和这条软件栅格路径链接，再把页面像素交给 Qt 视口。

合入 #285 后核对 14 项目标产物、编译配方和源锁，复用同一目标 ELF。另从 `95bde71d`
构建普通 ISO `3a5ea2a60c3d852b`，复验实际像素、FAT 和资源回收。
[主线组合复验](../reports/clarke_skia_raster_mainline_20261126/manifest.json)
