# af0f64ef · Mobius v2 同修订 XPK 的可搬移构建回执

构建器保留两个 ELF 的原始命令参数和输入路径，便于审计和实际复链。打包器
核对 ELF 和本地输入后，从这份回执计算逻辑路径配方摘要，绑定源码、SDK、
profile、Widgets 套件、构建目录和相应交叉工具。包回执记录配方摘要与产品
修订号。历史回执继续按原文件摘要核对。

## 同修订重现

依照 CPython 固定配方的做法，两次使用冻结工具和同一输入摘要。这里用两个
断网 Linux arm64 接收容器分别搬移源码、SDK/profile、Widgets 套件及输出目录，
用 `--jobs 1` 只构建 Mobius 桌面和会话，再打相同修订 0 的私有 XPK。两次都
从 #381 确认的 Qt v2 归档开始，继续使用其静态归档与目标回执。
[CPython 固定配方](cf828683_glibc_v2_cpython_receiver.md)
[先前 Qt v2 验收](74efcc27_mobius_widgets_v2.md)

两个 XPK 均为 35,840,000 字节，跨容器 `cmp` 通过。两份包的 49 个纳管成员
均按同一 profile 校验，内嵌回执和其配方摘要相同。两组本地原始回执分别保留各自
路径及摘要。桌面和会话 ELF 的 SHA-256 都与 #381 的 QEMU 输入完全一致。
用第二个接收方同一对 ELF 再打修订 1，唯一改变的纳管文件是包回执中的修订号。
本轮实测停在宿主包校验和复链，客体证据仍对应 #381 的实际包。
[精确摘要、包比对及原始回执摘要](../reports/mobius_widgets_v2_reproducible_20261127/reproduction.json)

## Qt 替换材料与 Curvive

沿用 v1 已验的 `product_relink.py stage` 和 `relink`，从第二个接收方的
真实 Ninja 链接命令及原始回执暂存 186 项材料。包含两个程序的 12 个对象、
12 个 Qt 链接输入、13 个 SDK 链接输入，以及锁定 QtBase 原档、XOS 补丁和
对应声明。用材料清单的原输入复链，两 ELF 均与该接收方的原始 ELF 逐字节相同。
[v1 同输入复链](2d4bde25_mobius_unified_widgets.md)

公开的 Qt LGPL 替换材料仍需确认适用源码与对象的分发清单，并实测接收方
用兼容的修改版 Qt 归档完成替换和复链。当前的复链门核对原输入摘要和原 ELF，
覆盖相同材料的重现。Curvive 原 PNG 和嵌入桌面 ELF 的 BMP 与 `c83900e0`
字节一致，现有记录只有 GUI-Desktop 快照及 Git 导入线索，缺少版权人以及
授权条款。现有私有包范围和公开分发门继续适用。
[Qt 声明与材料契约](../../src/ports/qt6/redistribution_manifest.json)
[Curvive 来源记录](../reports/mobius_unified_widgets_20261127/curvive_audit.json)

复现沿用 [Mobius 的 SDK 打包入口](../../src/ports/aurora_desktop/README.md#build-from-a-relocated-widgets-kit)，
固定 Qt 套件 SHA、SDK/profile、源码、交叉工具、并行数和产品修订。分别在两个
不同目录构建和打包，再对两个输出执行 `cmp`。对应的完整索引不含私有二进制。
[证据索引](../reports/mobius_widgets_v2_reproducible_20261127/manifest.json)
