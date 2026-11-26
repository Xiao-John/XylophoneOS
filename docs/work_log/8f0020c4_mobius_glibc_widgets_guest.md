# 8f0020c4 — Mobius glibc Widgets guest

2026-11-26 · 源码基线 `2d8b2356`。迁移现有单窗口 Mobius 界面和普通会话父程序，
使用隔离的 glibc C/C++ SDK 与 Qt Widgets 6.8.3。Qt/QPA 构建仍直接使用现有
Mobius、Aurora 样式、资源和 Interactium 源码。

## 构建

目标 Widgets kit 与 [G07 QtBase](48bcc2f4_qt_e19_glibc_target_qtgui_packages.md)
使用相同版本的 QtBase 源锁、宿主生成器和隔离 glibc 工具链。用
`prepare_widgets_source.py` 校验并准备 QtBase 源树，再应用 `glibc_qtcore.patch`
和 `quick/glibc_qtbase_platform.patch`。为 Core、Gui、Widgets 新建目标构建与安装
目录。采用 G07 的 glibc QtBase 参数，启用 `FEATURE_widgets` 并关闭
`FEATURE_filedialog`。禁用预编译头，使用 Ninja Release 和静态归档。

```sh
cmake --build "$WIDGETS_BUILD" --parallel 3
cmake --install "$WIDGETS_BUILD"
python3 src/ports/aurora_desktop/glibc/build.py \
  --sdk-build "$GLIBC_SDK" --sdk-profile "$GLIBC_PROFILE" \
  --qt-build "$WIDGETS_BUILD" --qt-prefix "$WIDGETS_PREFIX" \
  --qt-source "$QTBASE_SOURCE" --host-qt "$HOST_QTBASE" --output "$MOBIUS_BUILD"
```

构建入口核对完整 SDK profile、GCC/G++ 和 binutils 摘要、原生 moc/rcc 版本、
QtBase 构建配置及安装归档。应用 CMake 固定 Core、Gui、Widgets 和四个随带归档，
在编译前核对实际导入归档和工具路径，编译后再次检查输入摘要和两个二进制的静态
x86-64 ELF 布局。共享的 `xos_link_qpa` 只负责已有 QPA、字体资源和静态插件导入。

会话程序的单独链接预检发现 glibc SDK 缺少 `spawn_file_diagnosed` 和 `spawn_file`。
该程序从当前源码交叉编译现有 XOS ELF 装载、TLS、文件客户和文本输出源文件，并要求
glibc 的 `xos_file_session_exchange` 符号，使装载与 libc I/O 使用同一文件服务会话。
Qt 和会话均使用同一 glibc sysroot，公共 ABI 沿用现行实现。

SDK 的 glibc 2.44 和 GCC 16.2.0 上游签名验证回执分别为 `ec2fefec…` 和
`4deed527…`。构建使用 CMake 4.4.5、Ninja 1.13.2 和 6.8.3 原生生成器。

| 输入与构建产物 | SHA-256 |
| --- | --- |
| glibc C/C++ SDK manifest | `7eee04884a96ced6de12d20794af6809f544e3f15bc4e409b4197e58b1583d7a` |
| glibc SDK profile | `5dde8b7cd0a2e5fe9d0db892b81f88eeed36e2f72ba89826209acb013362b10a` |
| Widgets kit `libQt6Core.a` | `584ac69437bef6bb91ae34f702477be7270ac022333b0faf8755e08e4313add3` |
| Widgets kit `libQt6Gui.a` | `706310c95604312db68044f86a11ce1a10a32d13590104bc23057913193d3eb7` |
| Widgets kit `libQt6Widgets.a` | `c5591b8cf44d273fe5309dee753133da7b20c0ed79da06023ae9b5b53a32fcba` |

## 客体

使用既有 d87 默认组合系统 `d82908b725ffd19a` 的只读 ISO。测试脚本核对系统清单和
两个 ELF 的摘要，并在独立 FAT32 盘导入桌面和会话父程序。

```sh
python3 tests/mobius_glibc_guest.py --system "$D87_SYSTEM" \
  --target "$MOBIUS_BUILD" --output "$MOBIUS_GUEST"
```

QEMU 11.1.3 单核 TCG 初次运行验证了预览入口。会话父程序已启动，原 90 秒限时内
桌面未就绪。既有装载器逐页读取 24,665,043 字节的可加载段，glibc 文件连接在等待
旧版文件服务响应时使用单调时钟睡眠。复验沿用同一 ISO 和两个 ELF，为会话入口留出
360 秒，并分别记录发命令到 `DESKTOP_READY` 的宿主耗时和桌面内的启动采样。

| 入口 | 宿主就绪耗时 | 桌面采样 | 退出后资源 |
| --- | --- | --- | --- |
| xsh `exec-file /usr/bin/mobius.elf` | 17.988 s | 1,730 ms，9,006 页，3 线程 | `[121635, 5, 3]` |
| xsh `exec-driver /usr/bin/mobius-session.elf` | 192.577 s | 1,560 ms，9,040 页，3 线程 | `[121635, 5, 3]` |

两条入口均实际收到 PS/2 `Ctrl+,`、`Ctrl+D` 和 `Ctrl+Q`，打开外观页、切换 Daybreak、
关闭桌面。两条入口取得相同的两张 VGA scanout。Midnight 与 Daybreak 的亮像素数量
分别为 10,293 与 432,916。输入线程均 join，xsh 等到正常退出 0。串口确认会话父进程
创建了桌面子进程。停止 Display 和 Interactium 后系统基线恢复到 `[129711, 3, 1]`。

| 元素 | SHA-256 |
| --- | --- |
| d87 组合系统 ISO | `64230b48317bb327fcac03651982381b98912da10a3256e98b73d7d3091fa1f5` |
| d87 系统清单 | `70f7ba2a3d9b1607269a73dbbc9a79278297819624539547a2114b444e42601c` |
| 桌面 ELF | `9fdacb77d2dc935a83150d68f6275cc355f50cd3c8b693b7eb2e7529a612a413` |
| 会话 ELF | `63ae70d23458697d6d971d780b13382765e601182fec899a5905d0b528a9fdc4` |
| 桌面构建回执 | `3f6ffda5f68f839cab3c590a2656c9de61e6376da4345efddff83018577c8483` |
| 会话构建回执 | `efb141656b828823d5ffcd49f1c29679608ea3e1902e0eb49e7efebe9051ddf5` |
| 首轮超时回执 | `df7eb6fcf13c0c1599013f1c86331bc06e5880e3d3d17d55a1a6a314698ffd2c` |
| 复验客体回执 | `b33fdf594cbc5309bc98c8ef0654b868e19bce91b2e4622eddbba6308d77c0ef` |
| 复验串口 | `fb7c9ca2cf3b44b0ef752389c720f9851a5077f3cb8d051ae089ed815f1b86f7` |
| 两张去重 VGA 截图压缩包 | `58c662e18d86f449ec8697e66e28e039bae3f0974ae59b448b072d3437e3492a` |

压缩构建日志、两轮原始回执及去重截图保存在本地 `build/qt_glibc/mobius_e17/`。
会话加载耗时需单独改善。Notes、ClarkE、Studio 的会话内应用切换和新组合系统待验。
用两种真实 glibc 路径尝试既有 `package_desktop_products.py` 时，sysroot 缺少该入口所需的
内置 `manifest.json`，SDK 构建根的 manifest 则缺少旧版 `compiler` 字段。glibc XPK
安装、升级、卸载以及正式分发仍需独立验证。
