# 2d4bde25 · Mobius 的统一 glibc Widgets 构建

沿用正式 `xos.mobius` 桌面与会话、Aurora 共享框架以及两个原路径。
以已合入 #333 和 #339 的主线 `e1c08c67` 为起点，使用统一
`xos-x86_64-glibc-unified-cxx-v1` 的已绑定 SDK 和 Qt 6.8.3 源。
将原 QtBase 构建图复制到隔离 Linux 文件系统，在私有副本启用 Widgets、
关闭 FileDialog。构建图重新执行受影响的 Core、Gui 和 Widgets 编译。
接收方需要 Widgets 前缀、同版宿主工具、统一 SDK 和 Mobius 源码。
[构建、XPK 与复链命令](../../src/ports/aurora_desktop/README.md#build-from-a-relocated-widgets-kit)

## 对应声明与壁纸来源

现有 Qt 13 份通用许可文本按发行清单核对。Qt GUI 的 18 份许可或来源声明
与锁定 QtBase 原档逐字节一致，包含实际用到的 FreeType、HarfBuzz 和
DejaVu Sans。新开发套件和私有 XPK 携带这些声明。XPK 同时保留对应 SDK
的运行库文本、Qt 源锁和生成的 Aurora 壁纸记录。

Mobius 同时使用另一份 Curvive 壁纸。保留的 PNG 与嵌入的 BMP 均首次见于
`c83900e0`，Git 导入作者为 `lceng26`，该提交和当前的两份图像字节一致。
相邻 README 和 `upstream.json` 将其描述为本地 GUI-Desktop 快照中的原图，
PNG 无 EXIF 或文字块。现有文件未记录这项素材的独立许可依据，仍需完成产品
分发资格核对。现有构建和私有验收保留素材与正式界面。
[引入 PR](https://github.com/Xiao-John/XylophoneOS/pull/90)
[壁纸核对](../reports/mobius_unified_widgets_20261127/curvive_audit.json)
[Qt GUI 声明核对](../reports/mobius_unified_widgets_20261127/qt_license_audit.json)

## 独立接收和复链

隔离生产端静态安装约 21 MiB 的 Qt Widgets 归档。两个禁网 Linux arm64 接收方
各在新的位置解包，独立编译同一 Mobius 桌面和会话，未挂载原 Qt 源树、原构建
目录或生产端的 Qt 前缀。两次桌面和会话分别产生字节一致的 ELF。两个 XPK
采用相同包 ID，分别为修订 0 和 1，均含 49 个纳管文件和 46 份声明材料。
升级替换实际包记录和纳管构建回执，保持可重复构建得到的产品 ELF。

以修订 1 的实际 Ninja 链接输入制作 Mobius 专用材料。它绑定 QtCore、QtGui、
QtWidgets、随带依赖、资源初始化对象和 SDK 静态输入。第三个禁网 Linux arm64
目录只获得材料和匹配交叉工具，复链的两份 ELF 与两包中对应文件逐字节一致。
篡改 Widgets 归档被拒绝。错套件清单摘要和真实 Qt Quick 套件也在构建前被拒绝。
[前缀与 XPK 摘要](../reports/mobius_unified_widgets_20261127/binding.json)
[产品材料清单](../reports/mobius_unified_widgets_20261127/materials_manifest.json)
[实际复链](../reports/mobius_unified_widgets_20261127/relink_receipt.json)

## 工作盘安装、升级和回退

用普通 ISO `5eb564c5a0ef2a4f` 做三次 Linux QEMU 冷启。每次将各自 XPK 的
安装清单、纳管文件及两个 ELF 从 FAT 盘读回对照。xsh 和 Dash 均实际打开桌面，
使用 PS/2 切换主题并退出 0，采样到不同的 Midnight 和 Daybreak 画面。各次
程序退出后回到 `121620 / 5 / 3`，停止图形服务后回到 `129696 / 3 / 1`
（空闲页、任务、完成项）。

安装和回退的直接入口用时 12.498–13.781 秒，升级后的两入口用时 12.183 和
12.001 秒。升级盘另通过 xsh 的显式授权入口运行正式会话，启动用时 122.311 秒。
会话使用本候选的 v1 SDK 文件等待实现，外部 Dash 来自另外绑定的新文件等待
SDK。两个构建身份各自记录。产品的 v1 源、Kit 和 XPK 与后续统一 SDK v2 分开。

真实历史 Mobius XPK 在统一 profile 核对时被拒绝。同一统一 profile 的升级
保留原外观文件，升级后新写入的用户文件在卸载和重装原包后仍能逐字节读回。
初始工作盘保持原摘要。
[三次冷启、盘事务和数据读回](../reports/mobius_unified_widgets_20261127/guest.json)

## 组合复验与重现

从主线 `f66021aa` 与 Mobius 源码 `7bfaee82` 的组合提交 `aa39befa`
重建普通镜像 `3b72216a00fc7f3c`。同一个 v1 修订 1 XPK 装入新工作盘，
逐项核对 49 个纳管文件、两个 ELF 和原外观文件。xsh 及 Dash 的启动分别
为 17.235 和 16.677 秒，PS/2 切换主题产生与三次冷启相同的画面摘要，
停止图形服务后恢复到启动基线。
[首轮组合复验](../reports/mobius_unified_widgets_20261127/current_combination.json)

主线 `8e66789c` 合入 #342 的 GNU Seed 发行改动后，从组合提交 `4260ade9`
再次重建普通镜像 `f95f1b94ad67ae45`，核对 2029 个系统输入。修订 1 XPK 的
49 个纳管文件和原外观文件逐项读回。xsh 及 Dash 的启动分别为 17.217 和
19.115 秒，画面与前次实测一致，停止图形服务后恢复至该镜像的
`129709 / 3 / 1`。v2 的 Widgets 套件、Mobius 和客体需要单独重建与验证。
[GNU Seed 主线组合复验](../reports/mobius_unified_widgets_20261127/gnu_seed_mainline_combination.json)

沿用构建指南的套件、接收方、XPK 和复链命令。客体运行
`python3 -B tests/mobius_unified_widgets_guest.py`，传入重建的 `--system`、
套件清单、v1 profile 和 SDK、两个修订的 XPK 与对应产物、Dash 的 ELF 和回执，
以及旧包作为拒绝样本。组合只运行修订 1 的安装与双入口，使用同一个
`run_mobius` 客体助手。组合普通镜像使用
`python3 -B scripts/build.py --output-dir "$SYSTEM"` 重建。客体运行于
Linux 上的 QEMU 11.1.3。
公开材料记录串口、画面摘要和资源计数，原始画面保留在私有验收目录。
公开客体 JSON 移除了瞬态工作盘位置，保留原件 SHA-256 和变换说明。套件、
复链材料和回执的公开快照标记了各自原件，保留原始交付对象的 SHA-256。
下一步核对 Curvive 的分发许可并重建 v2 的同等验收输入。
[证据根清单](../reports/mobius_unified_widgets_20261127/manifest.json)
