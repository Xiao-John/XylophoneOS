# glibc 默认发行验收表

以 [0.0.2-1103 发行清单](next_release.md)、[发行配方](playbook.md) 和
[组件许可台账](../licensing.md) 为准，核对发行资产和 `release_smoke.py` 实际运行的
软件。新候选的完整清单应绑定同一份系统、SDK、包 profile 和安装介质。独立候选
回执用于定位已经通过的场景，最终随包资产使用自己的回执。

## 上一版发行实际覆盖的软件

| 发行内容 | 已有证据 | 默认切换前的验收 |
| --- | --- | --- |
| 普通 ISO、安装 ISO、dash、日用命令和 xypm | 统一 SDK 的普通与安装 ISO、dash 命令替换、13 个工具、XPK 读回、卸载以及双代 profile 拒绝已验。 [代表应用矩阵](../work_log/d6ead81f_glibc_profile.md) | 用最终发行镜像复跑自动安装、空盘与有数据盘冷启、命令替换和基线回收。确认各 XPK、工具和 profile 与镜像 manifest 字节绑定。 |
| GNU Make、GNU Seed、宿主 SDK | 当前 Make 已从锁定签名源重建并运行真实 dash 配方。统一 SDK 已完成静态 C/C++ 交叉构建及隔离搬移。历史发行另有客体 `gcc`/`g++`、Binutils 和 `/sysroot`。 [统一 SDK 和代表应用](../work_log/d6ead81f_glibc_profile.md) | 在最终发行的工作盘从客体运行 C/C++ 编译器和 Make，检查产出确用选定 sysroot；将接收方 SDK 搬出源树，复跑 C/C++ 和 SDK 自带 XPK 工具。归档实际 GNU/工具链版本、补丁、例外和成员材料。旧 Seed 仅在有独立盘、 profile 与发行身份时保留。 |
| CPython 核心和标准库 | 历史 stock fork 的 3.14.9 静态解释器、XPK 上的 558 成员标准库和原生卸载已验。 [历史客体](../work_log/bbf38ffb_cpython_stock_glibc_guest.md) | 用统一 SDK 重建 CLI 和 XPK，在真实 stock 工作盘冷启后通过标准库、时钟、线程及用户文件测试。验证独立回退和包拒绝。 |
| 已发版 Python 依赖 | `stage_py3_b` 和 `python_idna` 进入 0.0.2-1103。发行 smoke 运行 `zlib`、`gzip`、压缩 ZIP 和 IDNA。当前 glibc 静态核心仅覆盖已选标准库与 stored ZIP。 [发行回执](next_release.md#002-1103-打包状态2026-11-04) · [Python 构建与分发](../plans/cpython.md) | 用统一 SDK 重建静态 zlib 模块，绑定同一 profile 重打 idna wheel 的 XPK。用同一工作盘跑原有发行用例，覆盖旧文件/压缩数据读回和卸载保留。源、补丁、PSF/zlib/BSD 声明对应实际随包内容。 |
| Qt 静态资产 | 上一版发布单独 Qt 资产。当前 Qt Quick 已在既有 profile 上验证源包、重链接样例和接收方安装、替换与回退。 [Qt 上一版审查](../licensing.md#qt-静态分发审查2026-11-03) · [Qt Quick 接收验证](../work_log/4d6f124f_qt_quick_receiver_install.md) | 随默认 ABI 同发时，从统一 SDK 重建并跑实际 GUI 用例；继续独立交付时，单独绑定其兼容 profile、启动入口和数据盘。用最终归档验证实际源码、补丁、成员许可、接收方重链接和安装说明。 |

CPython 的 Pillow、SQLite、其他压缩模块及扩展，ncursesw/Vim、Mobius、ClarkE
等继续按其各自计划验收。纳入发行清单时，同样绑定实际包、profile、系统、客体与
材料回执。[端口账本](../ports_ledger.md)

## 整套资产的发布门

| 关口 | 要求的实际证据 |
| --- | --- |
| 同一套候选合并验收 | 绑定发行 ISO、安装 bundle、初始盘、宿主与客体 SDK、全部随包资产及各自 profile 的 manifest。从干净盘和复制的旧数据运行发行 smoke。记录通过、失败、未运行的条目及对应摘要。 |
| 可替换的静态运行库 | glibc 已完成隔离的 C SDK 源码重建与实际替换重链接样例。发行材料按最终 C/C++ SDK 和所发静态程序逐项验证源码、对象、编译/链接配方及接收方复跑。许可、例外及告知按最终资产的条目收录。 [glibc 重建与重链接](../work_log/d25c5def_glibc_detached_source_rebuild.md) |
| 升级与回退 | 用最终 profile 重跑原生包升级和可恢复中断；已有同 profile 的 P2→P3 历史证据。保存新旧工作盘和用户数据读回。冻结 v0.0.1-1024 newlib 保持原 SDK、原介质和原盘，包管理继续拒绝跨 profile，回退使用独立盘。 [跨版本升级](../work_log/3ce98ac7_glibc_g4_xypm_p2_p3.md) · [冻结发行回退](../work_log/4ffa226d_glibc_stock_fork_frozen_rollback.md) |
| 发布记录 | 对实际发行资产重跑许可材料检查、接收方复验与 `CHECKSUMS.sha256`。记录源包获取方式、最终 SHA-256、未关闭条目和各条适用范围。动态装载的资格按 D0–D4 单列，随静态发行时将支持范围写入发行回执。 |

当前默认发行仍由原配方生产。切换和 newlib 退役以完成上述实际证据和最终组合为准。
