# 05dfb2b9 · Mobius Qt v2 单库替换与普通客体

Mobius 复链入口可以按独立给定的清单摘要选用一个 Qt 归档变体。原材料、交叉
工具和链接计划继续逐项校验，变体从独立目录核验后暂存，只有指定 Qt 路径引用
变体。未使用该归档的程序必须保持原摘要。输出回执记录两套归档摘要和实际
变化的程序。同输入复链继续核对原始的两个 ELF。
[构建入口](../../src/ports/aurora_desktop/README.md#build-from-a-relocated-widgets-kit)

## 单个 QtGui 对象

从锁定 QtBase 6.8.3 原档提取 `qpainterpath.cpp` 及相邻的 `qpainterpath.h`
和 `qpainterpath_p.h`。两份头与已安装套件逐字节相同。取完整 Widgets v2 构建
留下的 `compile_commands.json` 中该文件的编译 argv，保留 v2 sysroot、交叉
工具、功能宏和编译参数，用套件的安装头及仓库 XOS mkspec 重放，得到与原
`libQt6Gui.a` 成员逐字节相同的控制对象。

随后应用测试补丁，只在壁纸代码实际调用的 `QPainterPath::moveTo` 位置输出
`QT_V2_REPLACEMENT_PAINTER_PATH`。重编同一文件并用 `ar rD` 替换归档成员。
两套 QtGui 归档均为 216 个成员，名称与顺序一致，唯一变化的是
`qpainterpath.cpp.o`，定义的全局符号及类型保持一致。早期的 BMP 解码探针
在普通客体中未触发，检查实际桌面绘制后换为程序化壁纸使用的路径绘制调用。
[测试补丁](../../tests/fixtures/qt6/qpainterpath_replacement.patch)

## 独立收件和客体

按 #385 的源与配方重收 186 项。184 项与原清单逐项相同，差异在两份应用
静态归档。本次 GNU ar 列表记录了成员时间。Qt 与 SDK 链接输入、两份原始
ELF 回执及链接顺序均一致，后续使用本次重收材料的精确摘要。断网接收方在
新位置核对材料并运行原样与替换两条复链，原样 ELF 与 #385 相同。错误清单
摘要、SDK 归档替换请求和被改动的变体归档均被拒绝，且未生成输出。替换后
只有桌面 ELF 的摘要变化，`mobius_session.elf` 仍逐字节一致。

在 `960fce43` 的普通 XOS 镜像上使用 QEMU 11.1.3 从两张专用 FAT32 试验盘
分别冷启。xsh 启动的原样桌面无标记，替换桌面出现标记 10 次。两个桌面均
成功首帧、PS/2 输入切换主题、退出 0。两对图像摘要分别一致，停止图形服务
后均回到空闲页、任务和完成项 `129709 / 3 / 1`。最终复链入口重复通过，回执
与 ELF 和客体输入逐字节匹配。
[编译、收件、拒绝及客体证据](../reports/mobius_qt_v2_replacement_20261127/replacement.json)

客体复验使用 `tests/mobius_qt_replacement_guest.py`，传入普通系统构建目录、
其对应源码目录、原样复链目录与替换复链目录。公开索引记录摘要，材料、原件
串口和图像在私有归档中核对留存。当前实测覆盖一个实际修改的 QtGui 归档。
正式分发仍需完成相应 LGPL 对应源码及材料清单，并补齐 Curvive 授权依据。
[证据索引](../reports/mobius_qt_v2_replacement_20261127/manifest.json)
