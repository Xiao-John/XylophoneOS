# ClarkE 的 WebCore 软件绘制

`software_context.patch` 适用于 `../source_lock.json` 锁定的 WPE WebKit 2.54.2。
在 XOS 的 `USE(SKIA)` 配置下，本补丁让覆盖的 WebCore 对象使用 Skia 软件画布、图像、
图案和绘制记录，并去掉这些对象内部对 GL、Ganesh 和纹理图集的依赖。需要 GPU 的渲染
模式与录制参数在入口处拒绝。软件记录保留 `SkPicture`、边界、透明度和缩放信息。

在已核验的源包解包目录运行以下命令。使用 WebCore 生成的头文件和平台配置，以 XOS
C/C++ SDK 编译，并将该配置的目标归档与软件 Skia 一起链接。

```sh
patch --batch --fuzz=0 -p1 -d "$WEBKIT_SOURCE" \
  -i "$XOS_ROOT/src/ports/webkit/page/software_context.patch"
```

绘制夹具 `tests/fixtures/webkit/software_recording.cpp` 使用同一 WebCore 配置。
它链接补丁后的 `SkiaRecordingResult.cpp` 和 `SkiaUtilities.cpp`，以及目标 Skia、
WTF、bmalloc、字体和编码依赖。先把链接结果存为 `software_recording.elf`，并将
ELF、夹具和补丁的 SHA-256 分别记为 `recording_link.json` 的 `elf_sha256`、
`fixture_sha256` 和 `patch_sha256`。客体检查会在启动前核对这些摘要和系统镜像。

```sh
python3 tests/webkit_software_recording_guest.py --target "$RECORDING_OUT" \
  --system "$SYSTEM_OUT" --output "$GUEST_OUT"
```

该夹具检查实际 Skia 录制回放、WebCore 混合模式、四个像素和资源回收。生成完整
WebCore 目标前，还需要在 `SourcesSkia.txt` 中处理 `SkiaPaintingEngine.cpp` 和
`SkiaReplayCanvas.cpp` 的 GPU 图集访问，并接通其他平台接口。页面解析、布局和 Qt
视口仍按 M2 独立验收。

## WebCore 软件构建目标

为整个静态目标应用 `software_context.patch`、`software_buffers.patch` 和
`software_graph.patch`。在通常的 XOS JSCOnly 交叉配置上启用
`XOS_WEBCORE_SOFTWARE=ON`。该选项启用静态 WebCore、软件 Skia 和 WebCore 的原生
请求值类型。软件缓冲区的创建和转移沿用上游对象，Canvas 请求加速缓冲区时沿用
WebCore 的软件回退。整页构建的源表选入软件字体、滤镜、绘制和缓冲区对象。GL、
Ganesh、纹理图集及协调合成器由其各自后端处理。

链接器使用 `XOS_SKIA_RASTER_ARCHIVE` 和 `XOS_SKIA_FONTCONFIG_ARCHIVE`。Skia 头来
自同一锁定源包下的 `Source/ThirdParty/skia`，用 `XOS_SKIA_INCLUDE_DIRECTORY` 指定。
在只搜索目标库的配置中提供 ICU 79.1、LibXml2、SQLite3、zlib、HarfBuzz 与
HarfBuzz ICU、Fontconfig、FreeType、PNG 和 JPEG。宿主生成器按原有方式从宿主环境
获取，Skia 归档和上述依赖均来自 XOS 目标构建。

```sh
cmake -S "$WEBKIT_SOURCE" -B "$WEBKIT_OUTPUT" -G Ninja \
  -DPORT=JSCOnly -DXOS_WEBCORE_SOFTWARE=ON -DENABLE_STATIC_JSC=ON \
  -DCMAKE_TOOLCHAIN_FILE="$XOS_WEBKIT_TOOLCHAIN" \
  -DXOS_SKIA_INCLUDE_DIRECTORY="$WEBKIT_SOURCE/Source/ThirdParty/skia" \
  -DXOS_SKIA_RASTER_ARCHIVE="$SKIA_RASTER_A" \
  -DXOS_SKIA_FONTCONFIG_ARCHIVE="$SKIA_FONTCONFIG_A"
cmake --build "$WEBKIT_OUTPUT" --target WebCore
```

`XOS_WEBKIT_TOOLCHAIN` 使用同一 glibc C/C++ kit 的 C/C++ 驱动和 sysroot，提供上述目标
库的 CMake 搜索根。编译器和原生 ABI 头的布置沿用
[JSCOnly 配置](../README.md#原生-llint-布局生成)。明确关闭 JIT、WebAssembly、采样
及宿主动态依赖搜索。软件配置在生成绑定前关闭 WebGL 和 WebGPU。重用早期的
CMakeCache 时，将 `ENABLE_WEBGL` 和 `ENABLE_WEBGPU` 两项设为 `OFF`。

## 本地整页验收

使用该配置生成的 WebCore 命令编译 `tests/fixtures/webkit/local_page.cpp` 和锁定
源包的 `Source/WebCore/testing/TestPage.cpp`，补上后者所在目录的头文件搜索路径。
将两个对象与完整 WebCore、同配置的 JavaScriptCore/WTF、PAL 和软件 Skia 等目标
归档链接成普通 XOS 应用 `local_page.elf`。链接回执 `local_page_link.json` 保存 ELF、
C++ 夹具、HTML、SDK manifest、SDK profile、源锁及三个软件补丁的 SHA-256。
字段名见客体运行器的 `inputs`。

```sh
python3 tests/webkit_local_page_guest.py --target "$PAGE_OUT" --sdk-kit "$XOS_SDK_KIT" \
  --system "$SYSTEM_OUT" --output "$GUEST_OUT"
```

夹具通过 WebCore 的测试页加载本地 HTML，检查两个 DOM 元素的 CSS 边界并调用
`LocalFrameView::paintContents` 绘制到 CPU 位图。客体分别读回原 HTML 和只改
叠层颜色的 HTML。第二次应到达像素检查、退出码为 11，两个进程退出后资源均须
回到基线。完整目标归档、此门的客体结果以及 Qt 视口仍待验证。
