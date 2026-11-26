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
