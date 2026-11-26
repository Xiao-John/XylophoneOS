# b9673c26 — Qt E19 external Quick application builder

Linux arm64 可搬移开发包的构建与双入口验收见
[870aabad](870aabad_qt_quick_relocatable_kit.md)。

2026-11-26 · Qt 6.8.3 · XOS glibc C/C++ 候选。独立应用通过普通 `qt_add_qml_module`
交叉链接，并在 QEMU 显示实际 Qt Quick 软件场景。应用源目录独立于 XOS 仓库、Qt 源码
和 Qt 构建树，使用搬移后的目标安装前缀。QtCore、QtGui、QtQml 与 QtQuick 沿用
[已验 G07](c8f43a1f_qt_e19_software_quick_guest_smoke.md) 的归档。

## 构建前置

目标前缀使用已安装的 QtBase Core、Gui、随带 FreeType、HarfBuzz、PCRE2、zlib 与其
CMake package、私有 QPA 头文件和静态资源对象。Qt Declarative 追加 QmlIntegration、
Qml、QmlMeta、QmlModels、Quick，保留各静态 QML 插件的 `qmldir`、CMake target、
初始化对象和资源对象。Quick 的上游安装目录也包含 `QtQuick.Window` 兼容模块。

应用用到宿主 `moc`、`rcc`、`qmlimportscanner`、`qmltyperegistrar`、`qmlcachegen`。
QtBase 宿主目录提供 Qt6CoreTools、Qt6GuiTools 和 Qt6HostInfo。另一个宿主目录提供
完整的 Qt6QmlTools CMake 导出及其引用的原生工具。`qsb` 在此前构建目标 Quick 库时
生成了场景图 shader，应用沿用这些目标资源。两份宿主 kit 均为 Linux arm64 Qt 6.8.3。

将已保存的 `target-qt-kit.tar.zst` 解压到新目录，或以已验 QtBase 安装与已构建
Qt Declarative 为输入来创建目标安装前缀。

```sh
mkdir "$APP_TARGET_PREFIX"
cp -a "$QTBASE_TARGET_PREFIX/." "$APP_TARGET_PREFIX/"
cmake --build "$TARGET_QML_BUILD" --parallel 2 --target \
  quickwindow quickwindow_init quickwindow_resources_1
for module in qmlintegration qml qmlmodels qmlmeta quick; do
  cmake --install "$TARGET_QML_BUILD/src/$module" --prefix "$APP_TARGET_PREFIX"
done

source_cmake="$TARGET_QML_BUILD/lib/cmake"
target_cmake="$APP_TARGET_PREFIX/lib/cmake"
# Qt Declarative 的根安装脚本生成的依赖与插件索引。
for module in Qml QmlMeta QmlModels Quick; do
  cp "$source_cmake/Qt6$module/Qt6${module}Dependencies.cmake" "$target_cmake/Qt6$module/"
done
for plugin in modelsplugin qmlplugin qtquick2plugin; do
  cp "$source_cmake/Qt6Qml/QmlPlugins/Qt6${plugin}Dependencies.cmake" "$target_cmake/Qt6Qml/QmlPlugins/"
done
cp "$source_cmake/Qt6Qml/Qt6QmlPlugins.cmake" "$target_cmake/Qt6Qml/"
cp "$source_cmake/Qt6Quick/Qt6QuickPlugins.cmake" "$target_cmake/Qt6Quick/"
```

## 独立应用

复制 [应用样例](../../tests/fixtures/qt6/quick_app/CMakeLists.txt) 的 CMakeLists、
`main.cpp` 和 `Main.qml` 到新目录。项目包含 `XOS_QUICK_SUPPORT` 并对可执行目标调用
`xos_link_quick_app`，链接现行 Interactium QPA，并内嵌锁定 QtBase 源包中的 DejaVu
字体。样例显式导入 `QXosIntegrationPlugin` 并选择 Qt Quick Software backend。

```sh
python3 src/ports/qt6/quick/build_app.py --source "$APP_SOURCE" --output "$APP_BUILD" \
  --target quick_app --target-prefix "$APP_TARGET_PREFIX" \
  --host-qt "$HOST_QTBASE" --host-qml "$HOST_QTDECLARATIVE" --qtbase "$QTBASE_ARCHIVE" \
  --sdk-build "$GLIBC_SDK_BUILD" --sdk-profile "$GLIBC_SDK_PROFILE"
```

构建入口核对 glibc SDK profile、六个目标工具字节、宿主生成器版本与 QtBase 源包。
配置后读取 CMake 解析出的实际目标归档、插件和宿主工具路径，逐个比对指定前缀。
构建结束后重新核对输入摘要，验证 x86-64 静态 ELF，并写出 `receipt.json`。

验证时环境中放入了另一组同为 Qt 6.8.3 的 QtBase/Qt Declarative 路径，实际生成器
和目标库均来自参数选定的前缀。将 `Qt6::Quick` 的 CMake 导入位置显式指向竞争归档后，
入口拒绝继续编译，未生成 ELF。正常构建执行了样例的 QML 类型注册和缓存源生成。

## 客体

使用 [G07 镜像](c8f43a1f_qt_e19_software_quick_guest_smoke.md)，启动 Display 与
Interactium 服务后，经 xsh `exec-file` 运行独立应用。首张截屏早于显示服务完成呈现，
后续在 2 秒内轮询 scanout，核对 800×600 画面、窗口颜色与 475 个文字亮像素。
Qt 软件首帧标记、定时退出 0、输入线程 join 和两次精确资源恢复均通过。
应用退出与服务停止后的资源计数分别为 `[121638, 5, 3]`、`[129714, 3, 1]`。
最后一轮使用压缩目标 kit 重新解出的安装目录，重复了独立应用的构建和客体验证。

| 产物 | SHA-256 |
| --- | --- |
| `target-qt-kit.tar.zst` | `7c0c63fa6698e7d699c45fb955438547896851ea6be5b9a1f29756da4f14f28c` |
| 独立应用 ELF | `5f6f1c203f4649ac3ee72e7a6329401f2856c1554ea3b5b6ead56e92861d8a9c` |
| 应用构建回执 | `ea6f224d788e52773a2da04f96c51fae104a5093f64502282659319ebf7b548d` |
| 客体回执 | `2f1a77b6bc60cbd1bc6f71a23be9be989caa5e9fbf87c4d70c3d1454540c4b8e` |
| 客体 scanout 原始 PPM | `ba0c16e426bb616c66cbd5985ac0d694eb07f9e4152195c066542968a4232aa1` |
| 客体串口日志 | `0b7b89007e07589b2287c728d4509079e3a3f253865c3a4d8d89d8715d59b546` |

本地产物位于 `build/qt_glibc/quick_e19/app/`。目标 Qt kit 包包含上述安装前缀，实际
应用构建仍显式绑定已验 SDK、宿主 kit、XOS 源码以及 QtBase 源包。许可分发和新 SDK
组合需要单独验证。

## 自定义输出目录

应用可在构建树内设置 `RUNTIME_OUTPUT_DIRECTORY`。CMake 生成所选目标的实际文件
路径，构建入口使用它核对 ELF，并在回执记录相对输出目录的路径。将外部样例的
目标输出指定为 `bin/`，重新交叉链接后，回执及命令输出均为
`build/bin/quick_app.elf`。该 ELF 的 SHA-256 为
`aa647692d5c04a9d7f79330aa4d7d276f817978c2197c13d7c30602d9c8e553c`。

将该 ELF 放入新工作盘，由同一 G07 ISO 的 xsh 启动。QEMU 显示 475 个文字
亮像素，scanout 原始摘要与上表一致。程序退出 0，输入线程完成 join，应用及服务
均恢复各自资源基线。新客体回执 SHA-256 为
`c7a6380901451cb8440398928ca62f841a0324c2f75910d6b8e1069f2ce08a2a`。
