# ClarkE WebCore 软件绘制与客体回放

2026-11-27。锁定的 WPE WebKit 2.54.2 以 XOS 的 `USE(SKIA)` 配置选择软件绘制。
原 `GraphicsContextSkia`、原生图像、图案与绘制记录在构建时引入了 GL、Ganesh 与
纹理图集。XOS 选择真实软件画布、图像和 `SkPicture`，并在入口拒绝加速模式或 GPU
代理。其他平台保留原实现。

补丁在重新提取的 7 个原始文件上以零 fuzz 应用，逐一匹配编译输入。10 个目标对象通过
交叉编译，其中含两种软件 ImageBuffer 后端，以及 WebCore 图形状态和颜色转换。
以统一 glibc C/C++ 候选 SDK 再建录制探针的两个 WebCore 实现和夹具，链接 CPU Skia、
WTF、bmalloc 及字形和编码依赖。QEMU 11.1.2 从新镜像 `cd5133fc02597a12` 启动，
从 FAT 读回 ELF 并核对摘要。真实录制回放核对红、黑、蓝、白四个像素、Multiply
混合模式、16×8 边界和录制参数。退出为 0，资源前后均为 `129696/3/1`。

独立复核从锁定源包重新应用补丁、校验 10 个对象和 25 个链接输入，并重新链接出同一
ELF。更改 ISO 或 ELF 摘要的输入在启动前被拒绝。复核还比较了七个上游文件的非 XOS
预处理分支与头文件集合，`SkiaUtilities.cpp` 的两个头文件调整了顺序。非 XOS 的完整
构建仍待验证。

完整页面仍待链接。两次部分链接使用相同的 23 个目标归档，加入 10 个软件绘制对象
和 2 个字体对象后，先前的 18 个未解析符号消失，新出现 87 个，剩余 2266 个。
后续以完整 WebCore 目标构建补齐对象和平台接口，再运行 DOM、布局、页面像素和 Qt
视口验收。两次部分链接数据不参与客体录制判定。

[补丁与客体复验说明](../../src/ports/webkit/page/README.md) ·
[构建、部分链接和客体回执](../reports/clarke_webcore_software_context_20261127/manifest.json)
