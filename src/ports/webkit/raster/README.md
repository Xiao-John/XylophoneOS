# ClarkE 的 Skia 软件栅格前置

从 WPE WebKit 2.54.2 锁定归档编译 Skia 的 CPU 源，按上游默认源表保留软件
绘制、文本和颜色处理。目标使用本地 glibc C/C++ SDK，复用已验 FreeType。
PNG/JPEG 从已锁 QtBase 6.8.3 的原始 C 源构建，png 链接锁定 zlib。
Skia 的 POSIX 选择是显式的，字体管理器用上游可注入字体数据的空目录实现。

宿主使用匹配 SDK 的 Linux ARM64 GCC、CMake、Ninja。`FONTS_OUT` 指字形依赖
验收使用的前缀与回执目录。客体入口使用从同一提交重建的 `SYSTEM`，需要 QEMU。

```sh
python3 src/ports/webkit/raster/build_target.py --webkit-archive "$WPE_ARCHIVE" \
  --qtbase-archive "$QTBASE_ARCHIVE" --zlib-archive "$ZLIB_ARCHIVE" \
  --font-target "$FONTS_OUT" --sdk-build "$GLIBC_BUILD" \
  --sdk-profile "$GLIBC_CXX_PROFILE" --output "$RASTER_OUT"
python3 tests/webkit_skia_raster_guest.py --target "$RASTER_OUT" \
  --system "$SYSTEM" --output "$GUEST_OUT"
```

验收以静态 Skia 产生的实际 12×10 像素为准，包含白底、裁剪蓝块和重叠红块。启动前
从 FAT 读回目标 ELF，出口核对资源。Qt 视口、WebCore 页面、编码图像解析和 GPU 路径
各自验收。随目标保留组件声明和原始成员摘要。
