# 从统一 glibc C/C++ SDK 构建 Qt Quick

XOS 静态 Qt Quick 使用两类产物。Linux arm64 的 Qt 6.8.3 宿主工具执行头文件同步、
MOC、RCC、QML 导入扫描、类型注册、缓存生成和 shader 处理。x86-64 XOS 的目标归档、
插件及最终 ELF 由 XOS 交叉工具和选定的 glibc SDK 构建。宿主工具的运行依赖由 Linux
提供。

旧的 Qt Quick 接收方已在 `xos-x86_64-glibc-thread-locks-cxx-v1` 验收。统一
`xos-x86_64-glibc-unified-cxx-v1` 涉及 pthread 和 C++ 配置头、CRT、libc、
libstdc++ 以及 unwinder 的实际字节变化。统一 profile 使用其自身重编的 QtBase、
Qt Declarative 和静态插件。原宿主生成器可从已核验的可搬移套件复用。

`xos-x86_64-glibc-unified-cxx-v2` 已通过重新构建目标前缀、断网接收和
普通 XOS 软件渲染客体验收。使用 v2 的 SDK 和 profile 一同重建，选择 v2
套件内的相同输入链接应用。[v2 构建及客体记录](../../../../docs/work_log/659b4dc2_qt_quick_unified_v2.md)

## 重建目标前缀

准备已通过校验的 Linux arm64 宿主工具套件、锁定 Qt Declarative 原档和统一 SDK 的
`sdk/` 与 `profile.json`。使用 SDK manifest 中的交叉工具及 CMake/Ninja。输出目录
使用 Linux 文件系统以支持 Qt 同步头文件的操作。

```sh
python3 -B src/ports/qt6/quick/build_target.py \
  --host-kit "$HOST_KIT" --declarative "$QT_DECLARATIVE_ARCHIVE" \
  --sdk-build "$UNIFIED_KIT/sdk" --sdk-profile "$UNIFIED_KIT/profile.json" \
  --output "$TARGET_BUILD" --jobs 2
```

构建器检查 SDK/profile、六项交叉工具、源归档、宿主输入和 Qt 配方，安装 QtBase
Core/Gui、Qml/Quick 及必要静态插件。沿用 XOS 软件渲染与原生 Interactium QPA。
目标安装前缀为 `target/`，记录为 `target_receipt.json`。中断后可用相同输入及
`--resume` 继续。QtBase 和 Qt Declarative 只在整个源码提取和补丁链完成后
发布到正式目录。若进程被强制终止，构建目录中遗留的隐藏暂存目录可以在构建停止后
清理。

## 在外部目录构建和搬移

将 [软件场景](../../../../tests/fixtures/qt6/quick/)的三个源文件检出到独立应用目录。
客体验收要求应用源目录与仓库逐字节匹配。用 Git 导出可以排除宿主文件系统生成的
元数据。先建立该目标前缀与应用的实际链接回执，再将相同内容组装为可搬移套件。

```sh
mkdir -p "$APP_SOURCE"
git archive HEAD:tests/fixtures/qt6/quick | tar -C "$APP_SOURCE" -xf -

python3 -B src/ports/qt6/quick/build_app.py --source "$APP_SOURCE" --target quick_probe \
  --target-prefix "$TARGET_BUILD/target" --target-receipt "$TARGET_BUILD/target_receipt.json" \
  --host-qt "$HOST_KIT/host_qt" --host-qml "$HOST_KIT/host_qml" \
  --qtbase "$HOST_KIT/qtbase.tar.xz" --sdk-build "$UNIFIED_KIT/sdk" \
  --sdk-profile "$UNIFIED_KIT/profile.json" --output "$REFERENCE_APP"

python3 -B src/ports/qt6/quick/quick_kit.py \
  --target-prefix "$TARGET_BUILD/target" --target-receipt "$TARGET_BUILD/target_receipt.json" \
  --host-qt "$HOST_KIT/host_qt" --host-qml "$HOST_KIT/host_qml" \
  --qtbase "$HOST_KIT/qtbase.tar.xz" --sdk-build "$UNIFIED_KIT/sdk" \
  --sdk-profile "$UNIFIED_KIT/profile.json" --application-receipt "$REFERENCE_APP/receipt.json" \
  --output "$STAGED_KIT"

tar -C "$STAGED_KIT" -cf - . | zstd -o "$KIT_ARCHIVE"
tar -C "$MOVED_KIT" --zstd -xf "$KIT_ARCHIVE"
python3 -B src/ports/qt6/quick/build_app.py --kit "$MOVED_KIT" --source "$APP_SOURCE" \
  --target quick_probe --output "$CONSUMER_APP"
```

搬移后的 Linux 环境提供相同交叉工具和仓库里的 XOS Qt 构建支持。开发者可以仅给
构建器新的套件位置与自己的应用源。构建器从新套件内选择宿主生成器、静态模块、
目标 SDK 和记录，并在链接完成后复核。

## 普通客体验收

```sh
python3 -B tests/qt6_quick_guest.py --image "$SYSTEM/xos-install.iso" \
  --system-manifest "$SYSTEM/manifest.json" --kit "$MOVED_KIT" \
  --app-receipt "$CONSUMER_APP/receipt.json" --payload "$CONSUMER_APP/build/quick_probe.elf" \
  --output "$GUEST_XSH"
```

以当前统一 SDK 构建的 Dash 回执可通过 `--dash-manifest` 在独立盘运行。
验收记录发起启动到首帧的耗时。默认首帧截止时间为 60 秒。在 QEMU TCG 下测量
大型静态程序通过 Dash 启动时，可以显式追加
`--dash-manifest "$DASH_MANIFEST" --first-frame-timeout 240`。
客体验证 QML 动画、文字、来自 QEMU PS/2 的键盘输入、同进程窗口关闭和重新打开，
以及应用、输入线程和图形服务回收。发行载体还须按实际随包的归档、源和对象材料验收
接收者重链接、安装替换和回退。
