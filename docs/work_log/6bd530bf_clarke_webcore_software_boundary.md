# 6bd530bf · ClarkE WebCore 软件绘制的编译边界

现有 WebCore 原生 `Page` 和几何探针已编译。整页链接仍依赖完整 WebCore 归档和
平台实现。主线的 Skia 软件栅格回执覆盖从 FAT 读字体及实际字形，文件流已能补齐
合法短读。
[字体流回执](e55d60c9_clarke_skia_file_stream.md)

在锁定 WPE WebKit 2.54.2 的同一目标配置下复核 `GraphicsContextSkia.cpp`。上轮缺少
`BitmapTexture.h`，本轮给编译命令加上真实上游 `platform/graphics/texmap` 头目录，
编译进入 `TextureMapperGLHeaders.h`，因缺少 `GLES2/gl2.h` 停止。传递链为
`GraphicsContextSkia.h`、`SkiaRecordingResult.h`、`SkiaGPUAtlas.h`、`BitmapTexture.h`、
`TextureMapperGLHeaders.h`。该试验只用了已有目标配置和 SDK，未生成绘制对象或运行客体。

软件路径接下来要将 GPU 图集依赖限制在实际合成路径，复用原生 Skia 软件画布。字体缓存
仍需要可复用的目标字体管理入口。验收顺序是目标绘制与字体对象、真正 WebCore 页面的
几何与像素、Qt/QPA 中有界的跨进程像素消费。继续采用锁定输入，并保留任何编译或链接失败。
