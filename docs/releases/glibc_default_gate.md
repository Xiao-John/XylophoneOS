# glibc 默认发行验收表

以 [0.0.2-1103 发布回执](release_0_0_2_1103.json)、[发行配方](playbook.md) 和
[组件许可台账](../licensing.md) 为准，核对发行资产和 `release_smoke.py` 实际运行的
软件。新候选的完整清单应绑定同一份系统、SDK、包 profile 和安装介质。独立候选
回执用于定位已经通过的场景，最终随包资产使用自己的回执。

## 上一版发行实际覆盖的软件

| 发行内容 | 已有证据 | 默认切换前的验收 |
| --- | --- | --- |
| 普通 ISO、安装 ISO、dash、日用命令和 xypm | 统一 SDK 的普通与安装 ISO、dash 命令替换、13 个工具、XPK 读回、卸载以及双代 profile 拒绝已验。 [代表应用矩阵](../work_log/d6ead81f_glibc_profile.md) | 用最终发行镜像复跑自动安装、空盘与有数据盘冷启、命令替换和基线回收。确认各 XPK、工具和 profile 与镜像 manifest 字节绑定。 |
| GNU Make、GNU Seed、宿主 SDK | 显式 glibc v1 发行配方已将 GNU Seed、同 profile XPK 与对应源码合装，接收方重开四份归档通过，组合客体通过原生 GNU 工具与 Python/zlib/IDNA。冻结 newlib 发行另盘复验。统一宿主 SDK 已完成静态 C/C++ 交叉构建及隔离搬移。 [GNU Seed 发行合装](../work_log/e2803194_glibc_gnu_seed_release.md) · [统一 SDK](../work_log/d6ead81f_glibc_profile.md) | 在最终发行的工作盘从客体运行 C/C++ 编译器和 Make，检查产出确用选定 sysroot；将接收方 SDK 搬出源树，复跑 C/C++ 和 SDK 自带 XPK 工具。归档实际 GNU/工具链版本、补丁、例外和成员材料。旧 Seed 仅在有独立盘、 profile 与发行身份时保留。 |
| CPython 核心和标准库 | 统一 SDK 已重建 3.14.9 静态 CLI、XPK 和 558 成员标准库。两套安装候选通过实际 stock 安装、重启、脚本、包互拒和卸载保留数据。 [统一 SDK 实测](../work_log/4d321863_glibc_cpython_unified_stock.md) | 在最终随包介质重跑当前核心入口，并与同 profile 的 Python 依赖组成以下发行脚本门。 |
| 已发版 Python 依赖 | 0.0.2-1103 的 smoke 运行 zlib、gzip、压缩 ZIP 和 IDNA。统一 SDK 的 3.14.9-1 已在普通 QEMU 跑通前三项和 zipimport，卸载后压缩文件可读回。显式候选入口已合装同 profile 的 daily、CPython 和 IDNA，两套安装及冷启分别核对 57 个文件。 [zlib 实测](../work_log/9739fdaa_glibc_cpython_zlib.md) · [发行合装实测](../work_log/9dd3de65_glibc_release_package_composition.md) | 将实际 zlib/IDNA、daily 和 Python 纳入同一候选清单，冷启前后运行历史发行脚本并核对许可、工作盘、卸载和用户数据。 |
| Qt 静态资产 | 上一版发布单独 Qt 资产。当前 Qt Quick 已在既有 profile 上验证源包、重链接样例和接收方安装、替换与回退。 [Qt 上一版审查](../licensing.md#qt-静态分发审查2026-11-03) · [Qt Quick 接收验证](../work_log/4d6f124f_qt_quick_receiver_install.md) | 随默认 ABI 同发时，从统一 SDK 重建并跑实际 GUI 用例；继续独立交付时，单独绑定其兼容 profile、启动入口和数据盘。用最终归档验证实际源码、补丁、成员许可、接收方重链接和安装说明。 |

CPython 的 SSL、Pillow、SQLite、其他压缩模块及扩展，ncursesw/Vim、Mobius、ClarkE
等继续按其各自计划验收。纳入发行清单时，同样绑定实际包、profile、系统、客体与
材料回执。[端口账本](../ports_ledger.md)

`package_release.py --glibc-candidate` 使用带真实安装验收的候选，验证三个包和
同一 profile，生成发行工作盘。两套候选以实际装配盘复跑了归属、离线安装、
冷启和发行 smoke。当前 `license_audit` 的范围为已登记材料与 SDK 中的副本，
最终候选应补齐统一 C/C++ SDK 的 GNU 上游、构建输入和随包静态程序清单。
[候选验收回执](../reports/glibc_release_package_composition_20261127/manifest.json)

显式 v2 静态候选已在 `8e66789c` 重建，并用同一发行初盘的副本完成包和原生
编译组合客体。接收方已重开四份归档并核对 GNU Make 签名。该候选的 P2 到 P3
自升级和发行盘原生包升级均通过同步中断、内置恢复和冷启重试。后续产品及完整
静态重链接材料继续使用最终选定候选验收。
[v2 复验记录](../work_log/9f6b0349_glibc_v2_release_inputs.md)
[升级与恢复复验](../work_log/cd9e6300_glibc_v2_upgrade.md)

## 整套资产的发布门

| 关口 | 要求的实际证据 |
| --- | --- |
| 同一套候选合并验收 | 绑定发行 ISO、安装 bundle、初始盘、宿主与客体 SDK、全部随包资产及各自 profile 的 manifest。从干净盘和复制的旧数据运行发行 smoke。记录通过、失败、未运行的条目及对应摘要。 |
| 可替换的静态运行库 | 已用 v2 发行 xypm 的实际 C++ 产物验证独立逐字节复链和 libc 成员替换，两个 ELF 均通过普通客体。最终发行仍须核对所有随包静态程序的对应源码、对象、配方与许可材料。 [实际发行 xypm](../work_log/7209d6e4_glibc_v2_release_xypm_relink.md) · [glibc 独立源码重建](../work_log/d25c5def_glibc_detached_source_rebuild.md) |
| 升级与回退 | v2 候选已通过 P2→P3 自升级和发行盘 IDNA 包升级的同步中断及恢复。历史 newlib 工作盘拒绝 v2 跨 profile 写入，原客体冷启可读。冻结 v0.0.1-1024 newlib 保持独立 SDK、介质和盘；工作区默认选择的三次冷启和原 XPK 重打包已通过。最终发行候选换版时重跑，保存新旧工作盘和用户数据回执。 [v2 升级](../work_log/cd9e6300_glibc_v2_upgrade.md) · [工作区回退](../work_log/50e9a5a4_glibc_sdk_default.md) |
| 发布记录 | 对实际发行资产重跑许可材料检查、接收方复验与 `CHECKSUMS.sha256`。记录源包获取方式、最终 SHA-256、未关闭条目和各条适用范围。动态装载的资格按 D0–D4 单列，随静态发行时将支持范围写入发行回执。 |

当前默认发行仍由原配方生产。切换和 newlib 退役以完成上述实际证据和最终组合为准。
