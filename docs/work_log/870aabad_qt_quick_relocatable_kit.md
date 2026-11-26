# 870aabad · Linux arm64 Qt Quick 开发包

2026-11-26 · Qt 6.8.3 · x86-64 XOS glibc。把已安装的目标 Qt、Linux arm64 的 QtBase 和
Qt Declarative 宿主工具、独立的 C/C++ SDK、SDK profile 及锁定 QtBase 源包整理进一个
候选目录。候选清单记录目标和宿主前缀的全部 SDK 文件内容、19 个直接模块与工具输入、
源包、许可清单和用于校核输入的首次应用构建回执。

`quick_kit.py` 先核对目标和宿主前缀的复制结果。首次搬移发现 Qt 安装产物的 CMake
导出仍指向原宿主安装目录，导致 QML 导入扫描器无法启动。候选副本把 Qt6CoreTools、
Qt6GuiTools 和 Qt6QmlTools 的 21 个宿主工具位置改为相对于各自 CMake 导出文件的位置。
工具二进制、目标归档与 SDK 字节保持一致。新的 `build_app.py --kit` 在配置前及链接后
重复核对候选树。原有的分项输入入口仍可用。

## 重建与使用

输入沿用 [Qt Quick 外部应用构建](b9673c26_qt_e19_external_quick_application_builder.md)
的目标安装前缀、两个匹配的宿主前缀和其实际链接回执。使用 Linux arm64 宿主上的 CMake、
Ninja、Python 及 SDK 清单绑定的交叉工具。实际验收使用 CMake 4.4.5 和 GCC 16.2.0。

```sh
python3 src/ports/qt6/quick/quick_kit.py \
  --target-prefix "$TARGET_QT" --host-qt "$HOST_QTBASE" --host-qml "$HOST_QML" \
  --qtbase "$QTBASE_ARCHIVE" --sdk-build "$GLIBC_SDK" --sdk-profile "$SDK_PROFILE" \
  --application-receipt "$REFERENCE_APP_RECEIPT" --output "$STAGED_KIT"
tar -C "$STAGED_KIT" -cf - . | zstd -o "$KIT_ARCHIVE"
tar -C "$MOVED_KIT" --zstd -xf "$KIT_ARCHIVE"
python3 src/ports/qt6/quick/build_app.py --kit "$MOVED_KIT" --source "$APP_SOURCE" \
  --output "$APP_BUILD" --target quick_app
python3 tests/qt6_quick_kit_guest.py --system "$SYSTEM" --receipt "$APP_BUILD/receipt.json" \
  --kit-manifest "$MOVED_KIT/manifest.json" --output "$GUEST_PROOF"
```

`MOVED_KIT` 是预建的空目录。`APP_SOURCE` 为复制到外部目录的
[Quick 应用示例](../../tests/fixtures/qt6/quick_app/)。双入口复验另用同一系统 SDK 重建
legacy dash，并为第二次运行添加 `--dash-manifest "$DASH_RECEIPT"` 和独立输出目录。

## 验收

冻结提交 `2b382380` 的源码、普通 ISO 和外部应用输入分别绑定。候选压缩包在断网
Linux arm64 容器内解包到新位置，原 Qt 前缀、原 SDK 源目录和原样例目录均未挂载。
CMake 配置、QML 导入扫描、类型注册、缓存源生成和普通静态链接通过。故意更改
候选内已绑定的 CMake 文件后，入口在创建输出前拒绝编译。混用 `--kit` 与分项选项
同样在创建输出前停止。
使用原有分项参数从同一归档另行配置和链接也通过，产物和构建回执单独登记。

普通镜像 `36fafd7e665ba3f8` 在 QEMU 11.1.2 用 xsh 和 legacy dash 各实际启动同一
ELF。两次都显示了 800×600 的真实 QEMU 画面和 475 个文字亮像素，输入线程正常退出。
应用结束后回到 `121633 / 5 / 3`，图形服务结束后回到 `129709 / 3 / 1`。
同一镜像按锁定版本执行 `make -o build smoke`，79 项常规检查和 10 份系统许可材料
检查通过，ABI 文档对照通过。

候选归档大小为 172,264,367 字节，SHA-256 为
`3706bf0fe13760f38eb50bcde6fd951c583479637f331000e96ff91090eba1c1`。归档保存在本地
`build/quick_kit/xos_qt_quick_linux_arm64_final.tar.zst`。
[构建、客体和许可证据](../reports/qt_quick_relocatable_kit_20261126/manifest.json)

许可核对覆盖 45 份登记材料、三个源锁及随包 QtBase 源码。Qt Declarative 和 Qt Shader
Tools 的完整分发源码、静态成员级许可及重链接验收仍待完成。链接器报告的 glibc
未支持接口保留于回执。QML 生成器报告的 32 类重复 C++ 类型描述与此前构建一致。
当前资格范围为外部软件渲染示例和两种 Shell 启动。

## 与 D1 首线程 TLS 合入后的主线组合

主线 `4706cc77` 合入之后，使用合成提交 `3f910178` 重建普通镜像
`e8d8379d3b342c9a` 及其 SDK 对应的 legacy dash。Qt 构建器、Qt 前缀校验、外部
示例和客体夹具与原验收一致。复用同一候选归档、SDK profile 和已封存应用 ELF。
两种 Shell 仍分别显示 800×600 与 475 个文字亮像素，并回到原有资源计数。
普通 smoke、系统许可材料检查与 ABI 文档对照也在新镜像上通过。
[主线组合回执](../reports/qt_quick_relocatable_kit_post291_20261126/manifest.json)
