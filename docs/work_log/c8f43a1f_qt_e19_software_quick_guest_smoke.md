# c8f43a1f — Qt E19 software Quick guest smoke

2026-11-26 · XOS `9f7a9a0f` · Qt 6.8.3 · G07 软件场景受限客体验证通过。
实际 Qt Quick、QtQml、QtGui 与 Interactium QPA 交叉链接为 x86-64 静态 ELF。
客体通过 QEMU VGA scanout 显示 QML 文本与动画，PS/2 键盘输入经 XOS 显示和
Interactium 服务送达场景。

## 构建与复现

复用 [E18 Qt Declarative 源和目标适配](d8bd3467_qt_e18_target_qml_and_vm.md)、
[原生 qsb](a95b1a20_qt_e19_host_shader_generation.md) 与
[隔离 glibc QtBase 目标 prefix](48bcc2f4_qt_e19_glibc_target_qtgui_packages.md)。
Qt Declarative 在独立目标构建目录中使用该 QtBase prefix 的 `qt.toolchain.cmake`
和相同 `XOS_GLIBC_*`、`XOS_SOURCE_ROOT`。`QT_HOST_PATH` 指向含真实 `qsb` 的
宿主 QtBase kit。设置 `QT_ADDITIONAL_HOST_PACKAGES_PREFIX_PATH` 与
`Qt6QmlTools_DIR` 指向 E18 原生 QML 生成器和对应的 CMake package。

Release、Ninja、静态，关闭预编译头、示例、测试、基准。E18 的 QML JIT、debug 和
worker script 保持关闭，另外关闭 `FEATURE_quick_shadereffect`、
`FEATURE_quick_particles` 和 `FEATURE_quick_designer`。这个构建树试验关闭 Qt
Declarative 的 `QT_GENERATE_SBOM`。启用的 QML animation 和宿主 `qsb` 使目标
Quick 构建实际生成场景图 shader。

```sh
cmake --build "$TARGET_QML_BUILD" --parallel 4 --target \
  Quick qtquick2plugin qtquick2plugin_init qmlplugin qmlplugin_init modelsplugin modelsplugin_init
```

构建 [`tests/fixtures/qt6/quick`](../../tests/fixtures/qt6/quick/CMakeLists.txt) 时继续使用
同一目标工具链和宿主工具参数。清理环境中的 `QT_ADDITIONAL_PACKAGES_PREFIX_PATH`
和 `QT_ADDITIONAL_HOST_PACKAGES_PREFIX_PATH`。用 CMake 参数把 `Qt6_DIR`、
`Qt6Core_DIR` 和 `Qt6Gui_DIR` 固定到目标 QtBase 安装，`Qt6Qml_DIR` 与
`Qt6Quick_DIR` 固定到目标 Qt Declarative 构建树。`QT_ADDITIONAL_PACKAGES_PREFIX_PATH`
使用目标 Qt Declarative 构建树，`QT_QML_OUTPUT_DIRECTORY` 使用其中的 `qml/`，
`CMAKE_MODULE_PATH` 与 `XOS_QTBASE_SOURCE` 使用同一 QtBase 源树的 `cmake/` 和根目录。
将夹具生成的 `qt_archives.txt` 与这四个明确路径比对后，构建 `quick_probe.elf` 并验证 ELF。

```sh
python3 tests/qt6_quick_guest.py --image "$XOS_IMAGE" --payload "$FIXTURE_BUILD/quick_probe.elf" \
  --output build/quick-e19-guest
```

## 客体结果

QEMU 11.1.3，TCG 单核、512 MiB、无网络。xsh 启动真实 Display 和 Interactium 服务，
以 `exec-file` 运行夹具。每次运行同一进程创建并销毁两个窗口，每个窗口都验证以下路径。

- Qt Quick 报告 Software backend。QEMU 采集到深蓝背景、DejaVu 字体绘制的真实字形
  和由 QML Timer 驱动的绿色矩形移动。
- QMP 键盘 `A` 经 PS/2 进入客体后，QML 键盘处理器将矩形变为橙色，scanout 确认
  颜色变更。键盘 `B` 允许退出场景。两次输入线程均 join，进程退出 0。
- 首轮两个场景呈现 6 帧、5 帧，字形区域各有 940 个亮像素，绿色矩形从 x=66 到 x=82。
  每个场景采样到 10,556 个进程用户页，页面大小为 4 KiB。100 ms 脚本定时器下，
  两个场景记录的最大相邻 `frameSwapped` 间隔均为 110 ms。该记录包含定时调度间隔。
  QPA flush 时间使用客体时钟，存在低于时钟分辨率的零值。
- 进程退出后资源计数恢复为 `[121638, 5, 3]`。两项服务退出后的系统基线恢复为
  `[129714, 3, 1]`。三列依次为可用页、任务、完成记录。
- 使用同一 ISO 与 ELF 新建测试盘并复跑，两个场景再次通过，分别呈现 6 帧、6 帧。
  两轮结果的页数采样和回收计数一致。

| 元素 | SHA-256 |
| --- | --- |
| Qt Declarative `libQt6Qml.a` | `0f5bdbf3e0ccc9e7d2d1906df5be5ab51851ae67ee68321e9752ba4014146a5d` |
| Qt Quick `libQt6Quick.a` | `5fb56984fab0bf937ae48de7bb900fb39f7f56222c216154a5f28b1c6dae2ec8` |
| QtQuick 静态插件 | `2c6014bb637102c4807e148f4b59f4c1f0440bb8dbbb47ef6c69b893668bd973` |
| 夹具 ELF | `441079cfe3c168dbf939f16a5700ce786ce45a6a6bda2fe4587691b2900699df` |
| XOS 镜像 `5def9f26dc747cdf` | `37403494630ea1e46eefd9a1f0950c372b05cc9945045c3aedbcf0bc2e279c3c` |
| 系统构建清单 | `7786c8d3f68c0075e6f7b361dc9cb0c0c55ee78e7460b312c768ff7693c9ab07` |
| 首轮回执 | `64a7357f1fea0f6d405477cc9f6669ab5c8fb047506e877fe4fe8237432fa050` |
| 首轮串口日志 | `f675568e19005f1e2f45925fae2bc9da6c92bc0a57a4de0a0f353f492840afda` |
| 首轮六张 scanout 压缩包 | `8638409b854785eba88e0fdbe17195fbc4aba77a43c0b9ef13085501dac03619` |
| 复跑回执 | `0cc098589337440928649aa211b0e7f13a94084635af2785cddde9840d8883fe` |
| 复跑串口日志 | `42ebb41eaf9bb88c74b4bfbadf1827f3774a77707b25af22b161473fced657ad` |

本地证据在 `build/qt_glibc/quick_e19/`。验收范围为 QML 文本、矩形、计时器、键盘、
两轮窗口与服务回收。Controls/Layouts、复杂场景、触控、IME、GPU、首次启动和空闲预算、
绝对内存峰值、长时压力与静态分发待验。
