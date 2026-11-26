# 0a9fa011 · glibc 应用 SDK 发布预览

发版入口的 `application-preview` 阶段组装和重验普通安装 ISO、可搬移的
glibc C/C++ SDK、v0.0.1-1024 原版 newlib SDK 归档及其冻结 profile。
重验从产物重算摘要，并复用 `package_glibc_sdk.py` 的完整 SDK 绑定。
冻结 newlib profile 保持对原系统 `2c3876e640840ff5` 的历史资格。
[发版手册](../releases/playbook.md#glibc-应用-sdk-发布预览)

## 组装和复验

在提交 `0a9fa0111de7b8957cc30d65f513d7d140f08ef0` 上以
`python3 scripts/build.py --quiet-demos-on-launch --output-dir build/release-proof/system`
重新生成普通镜像 `72a8c0f9fbad15a8`，复核其中 1,825 个源文件摘要。
运行 `license_audit.py --build build/release-proof/system`，登记材料关口通过，
开放项为 0。glibc 输入复用 #250 的已验证 glibc 2.44/GCC 16.2 C/C++ SDK
和匹配的 profile。newlib 输入使用与冻结发布记录匹配的原归档。
实际发版入口的组装和独立重验结果相同。
[组装回执](../reports/glibc_application_release_preview_20261126/assembly_receipt.json)
[#250 SDK 构建记录](245042e2_glibc_sdk_selection.md)

重验拒绝被修改的 ISO、冻结 SDK 归档、kit 启动器和客体资格字段。
启动器缺失执行权限也被拒绝。测试在独立副本尝试重建已有候选，原候选
仍通过校验。组装误传冻结 profile 时失败并清理半成品。
[拒绝路径回执](../reports/glibc_application_release_preview_20261126/rejections.json)

## 外部应用和普通镜像客体验收

断网 Linux arm64 容器 `xos-campaign-toolchain:linux-arm64` 从只读候选目录
初始化、构建、检查并打包源码树外的 C、C++ 和冻结 newlib 应用。冻结应用
重复打包得到逐字节相同的 XPK。QEMU 11.1.2 从预览目录的普通 ISO 三次冷启动，
用 xypm 在独立 FAT32 工作盘离线安装样例。dash 经由 PATH 和绝对路径启动
C、C++ 包，验证 C 读取用户文件和报告 glibc 2.44，以及 C++ 容器、线程和异常。
首轮自动回收四个演示进程和 44 页，第二轮运行回到相同的 129709 空闲页、
3 个任务、1 个完成记录。
[客体回执](../reports/glibc_application_release_preview_20261126/guest_report.json)
[dash 串口记录](../reports/glibc_application_release_preview_20261126/glibc_dash.serial.log.gz)

普通 ISO 分别在使用 glibc 应用前后启动冻结 newlib 对照 XPK。冻结 profile
拒绝 glibc XPK，glibc profile 也拒绝向冻结工作盘安装该包。拒绝后工作盘
的字节摘要一致。切回后，同一工作盘保留了原数据与第一次运行的追加内容。
这轮使用新候选 ISO 和冻结 SDK。下节记录随后的原版启动盘复验。
[冻结回退前](../reports/glibc_application_release_preview_20261126/frozen_before.serial.log.gz)
[冻结回退后](../reports/glibc_application_release_preview_20261126/frozen_after.serial.log.gz)
[保留的客体数据](../reports/glibc_application_release_preview_20261126/frozen-preserved-user-data.txt)

## 原版 v0.0.1-1024 回退复验

下载原发布镜像归档，按发布记录核对 80,661,910 字节和 SHA-256。归档中的
`xos.img` 是 BIOS 软盘镜像，与独立发布的 boot.img 摘要完全一致。
以原发行工作盘为输入，安装由冻结 SDK 重建的对照 XPK 到私有副本，
写入合成用户数据。QEMU 11.1.2 从原版软盘启动系统 `2c3876e640840ff5`。
使用旧版 `sup>` 的 `exec-file` 执行对照包，确认正常退出及同步。
[原发布资产记录](../releases/release_0_0_1_1024.json)

切换阶段从普通候选 ISO `72a8c0f9fbad15a8` 冷启动，使用另一块盘运行 glibc
2.44 的 C 应用。用 glibc profile 向旧盘安装该包被拒绝。回执记录旧用户盘在
切换前后完全相同的 SHA-256。继续使用同一旧盘、同一原发行软盘再次冷启动，
冻结 XPK 再次退出 0。同步后读回初始文件和按次序追加的 `before`、`after`。
两次旧版启动的应用退出后均收回资源，保持 130342 空闲页、2 个任务、
0 个完成记录。
[回执](../reports/glibc_release_1024_rollback_20261126/historical_rollback.json)
[首次旧版启动](../reports/glibc_release_1024_rollback_20261126/historical-before.serial.log.gz)
[glibc 候选启动](../reports/glibc_release_1024_rollback_20261126/glibc-switch.serial.log.gz)
[最后旧版启动](../reports/glibc_release_1024_rollback_20261126/historical-after.serial.log.gz)
[保留的客体数据](../reports/glibc_release_1024_rollback_20261126/preserved_data.txt)

本次交付覆盖本地发布组装和上述样例。默认 SDK 切换仍以迁移计划所列的
存量软件验收和完整组合验收为门。
[glibc 迁移计划](../plans/glibc_port_scout.md#从加固期走向默认切换的门)
