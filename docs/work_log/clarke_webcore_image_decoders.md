# ClarkE 的软件图像解码

XOS 软件 WebCore 接入上游 `ImageDecoders.cmake`，使用实际图像解码入口和 Skia
像素存储。静态 libwebp 1.6.0、demux、SharpYUV 由同一 glibc C/C++ SDK 构建。
发行原档的 201 个源码、构建和许可文件与上游 tag 的 Git blobs 一致。XOS 保留
libwebp 的 pthread 路径，目标 CMake 编译跳过裸 GCC 驱动不识别的 `-pthread` 参数。
[WebP 端口说明](../../src/ports/webkit/webp/README.md)

源准备从锁定的 WPE WebKit 2.54.2 重放。目标 CMake 图选出 WebCore 图像调度器、
可缩放解码器及 Skia 像素存储。PNG、JPEG、WebP、GIF、BMP、ICO 对象均通过实际
目标编译。AVIF 和 JPEG XL 可显式启用，所需目标归档和运行结果分别验收。

第一轮实际客体中，PNG 左上角预期 `ffff0000`，读回 `ff0000ff`，应用退出 1。
WebCore 以整数 `0xAARRGGBB` 写入小端像素内存。XOS 的 Skia 默认颜色类型将这些
缓冲解释为 RGBA。端口明确给这一解码缓冲标识 BGRA。对同一图像、同一 SDK 和
同一普通镜像重新链接并运行，检查 PNG 与无损 WebP 的四个包含 alpha 的像素，检查
JPEG 有损编码的颜色容差，并确认截断的 PNG 未交付完整帧。

链接使用目标 `ImageDecoder` 和相应解码器、`SharedBuffer`、色彩与矩形支持单元，
以及来自目标 SDK 的 PNG、JPEG、WebP、Skia、WTF 和 ICU 归档。复用普通 xsh 静态
ELF 客体运行器。

```sh
python3 tests/qt6_sdk_probe.py --image "$SYSTEM_ISO" --payload "$IMAGE_DECODERS_ELF" \
  --marker 'XOS_WEBKIT_IMAGE_DECODERS_OK png webp jpeg truncated' \
  --report "$IMAGE_DECODERS_GUEST_REPORT"
```

验收范围包括真实 WebCore 解码入口、目标静态归档和像素读回。完整 WebCore 链接、
页面中组合图像与 CSS 的显示、动画帧和 Qt 视口分别验收。
[源码绑定和两轮客体证据](../reports/clarke_webcore_image_decoders_20261127/manifest.json)
