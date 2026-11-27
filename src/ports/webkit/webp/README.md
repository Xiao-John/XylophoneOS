# XOS WebP 解码依赖

静态 WebCore 使用 [libwebp 1.6.0](https://developers.google.com/speed/webp/docs/compiling)
的 WebP 解码、容器 demux 和 SharpYUV 归档。用与 WebCore 相同的统一 glibc C/C++
SDK 和 x86-64 交叉工具从锁定的上游发行原档构建。构建器核对 SDK、工具和许可，
保留 pthread 支持。XOS 的 pthread 由 libc 提供，目标编译器省去宿主专用的
`-pthread` 开关。构建过程禁用上游命令行程序及其宿主依赖。

```sh
python3 src/ports/webkit/webp/build_target.py --archive "$WEBP_ARCHIVE" \
  --sdk-build "$XOS_SDK_KIT/sdk" --sdk-profile "$XOS_SDK_KIT/profile.json" \
  --output "$WEBP_OUT"
```

把 `WEBP_OUT/prefix` 加入 WebCore 交叉工具链的目标搜索根。CMake 要求 `WebP::demux`
和 `libsharpyuv.a`。分发静态库时保留 `prefix/share/licenses/libwebp` 中的 COPYING、
PATENTS 以及对应的锁定原档和 XOS 补丁。
