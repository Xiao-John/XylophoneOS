# 7d2642b5 · Mobius Widgets v2 构建输入与目标回执

从合入 #357 与 #358 的主线 `b0a92aab` 开始。共同的 QtBase 构建入口增加
`--component widgets`，使用锁定的 Qt 6.8.3、统一 glibc C/C++ SDK 和同版
Linux arm64 生成器。该入口在独立输出重编 Core、Gui 与 Widgets，并验证
`QT_FEATURE_widgets=ON` 和 `QT_FEATURE_filedialog=OFF`。已验 Qt Quick v2
的有效配置为 `QT_FEATURE_widgets=OFF`，其目标归档和配置头继续配套使用。
[Qt Quick v2 实测](659b4dc2_qt_quick_unified_v2.md)

复用的宿主套件已带 Qt 6.8.3 的 `moc`、`rcc` 和 `uic`。现有 `uic` 的
CMake 导出仍引用原构建路径。Widgets 建立一份小的可搬移导出，引用原套件
的生成器。构建回执记录有效配置、Qt 源码与缓存、已安装 Qt 树、三个宿主生成器、
六项交叉工具及 v2 SDK/profile。套件生产和接收都核对该回执，避免同一路径
中的另一版 sysroot 或 Qt 目标前缀被错误配给 v2。现有 v1 套件保留原契约。

## 本轮实测

Linux arm64 容器断网、只读挂载输入。使用 Python 3.14.10、CMake 4.4.5 和
Ninja 1.13.2 执行两条 `--check-inputs` 路线。真实统一 v2 SDK 和原宿主
套件的 Widgets 预检通过，保留默认选项的 Quick 预检也通过。预检没有生成
目标前缀。用真实旧宿主套件的 profile 配给同一 v2 SDK 时，入口在配置前以
`profile differs from the complete SDK binding` 拒绝。

| 输入 | SHA-256 |
| --- | --- |
| v2 SDK manifest | `a732380142271a3b92b949105285e76d4bdfb464ceb57358c66c95668139c3ce` |
| v2 profile | `2a2017b8f6b13f41952cee07cafe44ea9b946ed74aa1f5ed1c3359557ac112e1` |
| 原宿主套件 manifest | `6fc36b13ed96d8c7ec6e1ad8949e3c0216aea89abb9903fcc70816f646db3e51` |
| QtBase 6.8.3 原档 | `56001b905601bb9023d399f3ba780d7fa940f3e4861e496a7c490331f49e0b80` |

独立的 CMake 探针从新导出载入真实 `Qt6WidgetsTools` 包，解析 `Qt6::uic`
到只读宿主套件并运行，返回 `uic 6.8.3`。`tests/mobius_widgets_binding_host.py`
通过一个主用例和六个回执错配输入。既有 `tests/xypm_sdk_profile_host.py`
通过 45 项。私有日志在 `build/mobius-widgets-v2/`，主机新增约 36 KiB。

真实 QtBase Widgets v2 目标构建、离线重定位、Mobius ELF/XPK、复链和 QEMU
未运行。下一步在有足够空间的 Linux 构建目录执行完整 Widgets 命令，然后按
原 v1 已验路径重跑接收、复链和客体。Curvive PNG 及嵌入 ELF 的 BMP 与原导入
逐字节一致。公开分发需要补齐授权依据或采用授权明确的素材。
[操作指南](../../src/ports/aurora_desktop/README.md#build-from-a-relocated-widgets-kit)
[素材状态](../plans/mobius_unified_widgets.md#v2-的输入与分发边界)
