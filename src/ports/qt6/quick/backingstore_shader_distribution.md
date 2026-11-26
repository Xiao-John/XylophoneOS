# QtBase backingstore 着色器的重生成与分发材料

本页适用于 Qt Quick 6.8.3 套件里两个 `backingstorecompose` 着色器。锁定的 QtBase
6.8.3 源包在 `src/gui/painting/shaders/` 同时包含 GLSL 源、预编译 `.qsb` 和目录
`REUSE.toml`。QtGui 把两个 `.qsb` 纳入资源。两套 QtGui 归档、原始及双库替换后的
外部示例 ELF、Linux arm64 宿主 `qsb` 都已实读到原档的这两个 payload。
[官方 QtBase 发布包摘要](https://download.qt.io/archive/qt/6.8/6.8.3/submodules/qtbase-everywhere-src-6.8.3.tar.xz.sha256)

## 字节级重生成

准备 Qt 官方 Linux x86-64 `qsb` 6.4.0 和该发行的 QtBase、ICU 动态库，并使用套件绑定的
Linux arm64 `qsb` 6.8.3。分别在对应的 Linux 宿主环境运行命令，共享输出目录。下列 `SRC`
为上面已锁定的 GLSL 目录，`OUT` 为新建的工作目录。`QSB_64`、`QSB_68` 指向已校验工具。

```sh
for stage in vert frag; do
  QT_HASH_SEED=0 "$QSB_64" --glsl '100 es,120,150' --hlsl 50 --msl 12 \
    -o "$OUT/$stage.generated.qsb" "$SRC/backingstorecompose.$stage"
done
```

第二段使用套件的 6.8.3 工具。提取的 SPIR-V 来自上一步从 GLSL 新生成的包。
重序列化到 Qt 6.4 对应的 QSB v6 容器，并应用发行包中片段绑定项的历史序列化次序。

```sh
for stage in vert frag; do
  "$QSB_68" --extract spirv,100 -o "$OUT/$stage.spv" "$OUT/$stage.generated.qsb"
  cp "$OUT/$stage.generated.qsb" "$OUT/$stage.serialized.qsb"
  "$QSB_68" --qsbversion 64 --replace "spirv,100,$OUT/$stage.spv" "$OUT/$stage.serialized.qsb"
done
python3 -B src/ports/qt6/quick/backingstore_qsb_order.py \
  "$OUT/frag.serialized.qsb" "$OUT/frag.published-order.qsb"
cmp "$OUT/vert.serialized.qsb" "$SRC/backingstorecompose.vert.qsb"
cmp "$OUT/frag.published-order.qsb" "$SRC/backingstorecompose.frag.qsb"
```

该配方从 GLSL 复现发布归档的两个完整 `.qsb`。重新安排的是旧包中独立的 HLSL 和 MSL
资源映射项的写入次序。历史作者的完整命令和构建环境尚缺记录。
[Qt 6.4.0 分发目录](https://download.qt.io/online/qtsdkrepository/linux_x64/desktop/qt6_640/) ·
[Qt qsb 手册](https://doc.qt.io/qt-6.8/qtshadertools-qsb.html)

## 随成品的分发声明

QtBase 6.8.3 的 backingstore 顶点与片段着色器由 The Qt Company Ltd. 声明版权。发行包目录
的声明为 `LicenseRef-Qt-Commercial OR LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`。
配套材料保留该声明、QtBase 原始归档及生成配方。采用 LGPL-3.0-only 路径的成品需随包
标明 QtBase 的使用，提供 GPL 和 LGPL 许可文本，并以所采用的静态链接方式提供实际的对应源
与可重链接应用材料。按具体分发方式核对适用的安装信息。
[上游 REUSE 声明](https://raw.githubusercontent.com/qt/qtbase/v6.8.3/src/gui/painting/shaders/REUSE.toml) ·
[Qt 许可说明](https://doc.qt.io/qt-6.8/licensing.html)

宿主 `qsb` 的 Qt Shader Tools 入口源另声明 `LicenseRef-Qt-Commercial OR GPL-3.0-only WITH Qt-GPL-exception-1.0`。
对应的 GPL-3.0-only 和 Qt GPL exception 文本在套件 `notices/qtbase/licenses/` 中，与
Qt Shader Tools 归档中的文字逐字节一致。套件的源码与许可材料同时覆盖 qsb 链接的 QtBase
及着色器编译器组件。Qt 6.4.0 工具档案用于重生成验证，既有套件交付的是绑定的 6.8.3 宿主工具。各产品
所含第三方组件的传递许可及最终发布渠道按成品清单另行核对。
