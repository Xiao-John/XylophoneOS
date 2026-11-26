# a95b1a20 — Qt E19 host shader generation

2026-11-26 · Qt 6.8.3 · Linux arm64 Qt 构建宿主。E19 软件场景所需的原生
`qsb` 已构建并实测。Qt Declarative 使用它生成资源，即使客体选择 CPU 软件渲染。

- [Qt Shader Tools 源锁](../../src/ports/qt6/quick/source_lock.json)绑定 6.8.3 源包、
  `v6.8.3` 提交和 QtBase 提交。两个镜像取得的源包对上 Qt 官方
  [SHA-256](https://download.qt.io/archive/qt/6.8/6.8.3/submodules/qtshadertools-everywhere-src-6.8.3.tar.xz.mirrorlist)。
  QtBase 提交与 E18 目标构建及 Qt Declarative 的源锁一致。
- 宿主 QtBase 启用 Core、Gui，关闭 Widgets、OpenGL、Vulkan、EGL、XCB、
  FreeType 和 HarfBuzz。其静态 Core、Gui 和 `host_tools` 先构建，`qsb` 的
  [构建补丁](../../src/ports/qt6/quick/host_qsb_plugins.patch)将它的默认静态
  图片和平台插件导入关闭。`qsb` 本身使用 `QCoreApplication`，应用此补丁仍链接
  实际 QtGui、ShaderTools、glslang 和 SPIRV-Cross。
- 此构建直接复用 QtBase 的构建树。有完整 QtBase 安装时可用其安装前缀。构建树
  需要从同一 QtBase 源树补齐 `mkspecs/common`、`mkspecs/linux-g++` 和
  `cmake/QtFileConfigure.txt.in`（后者放在构建树 `lib/cmake/Qt6`）。
  Shader Tools 的 SBOM 装配在最小构建树内缺少已安装的 QtBase SBOM，故本地
  工具安装显式设置 `QT_GENERATE_SBOM=OFF`。

将校验后的源包解压到独立目录，从仓库应用上述补丁，然后构建和安装工具。
`QT_HOST_BUILD` 为宿主 QtBase 构建树，`QTBASE_SOURCE` 为同版本源目录。

```sh
patch -d "$SHADER_SOURCE" -p1 -i "$XOS_ROOT/src/ports/qt6/quick/host_qsb_plugins.patch"
cmake -S "$SHADER_SOURCE" -B "$SHADER_BUILD" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH="$QT_HOST_BUILD" \
  -DCMAKE_MODULE_PATH="$QTBASE_SOURCE/cmake" -DCMAKE_INSTALL_PREFIX="$QT_HOST_BUILD" \
  -DBUILD_SHARED_LIBS=OFF -DQT_BUILD_TESTS=OFF -DQT_BUILD_EXAMPLES=OFF \
  -DCMAKE_DISABLE_PRECOMPILE_HEADERS=ON -DQT_GENERATE_SBOM=OFF
cmake --build "$SHADER_BUILD" --parallel 3
cmake --install "$SHADER_BUILD"
"$QT_HOST_BUILD/bin/qsb" --version
"$QT_HOST_BUILD/bin/qsb" -o "$SHADER_BUILD/backingstorecompose.qsb" \
  "$QTBASE_SOURCE/src/gui/painting/shaders/backingstorecompose.vert"
"$QT_HOST_BUILD/bin/qsb" --dump "$SHADER_BUILD/backingstorecompose.qsb"
```

实测 GCC 16.2.0、CMake 4.4.5、Ninja 1.13.2。`qsb --version` 返回 `qsb 6.8.3`；
打包并反查 QtGui 的 `backingstorecompose.vert`，结果包含 Vertex stage 和 SPIR-V。

| 产物 | SHA-256 |
| --- | --- |
| Linux arm64 `qsb` | `0d3c86b8e7368f7a00d5b38ed7fc53d9826f800a8fd90889d858671d929c31b1` |
| `backingstorecompose.qsb` | `761932bbecd30ca043fdfaaeeaf4c1beac4c30c084c064002e9d10a3fd86648d` |

许可登记的 17 个路径和 10 份原始文件摘要已检查。宿主工具及生成物的分发审查、
glibc QtGui 目标链接和 Quick G07 客体测试仍各自待验。
