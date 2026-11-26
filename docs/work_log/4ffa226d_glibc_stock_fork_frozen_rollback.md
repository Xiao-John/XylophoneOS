# 4ffa226d · glibc C/C++ 候选与冻结 newlib 回退

候选构建之后，主线已合入 Qt Quick SDK。本轮从该主线 `31dae7e2` 的独立工作树运行验收，绑定普通候选 `3bbbf73984b95c20`、部署后的 glibc C/C++ SDK 和 `xos-x86_64-glibc-stock-fork-v1` profile。冻结输入是 v0.0.1-1024 的原发行 SDK、原 profile、原镜像归档和其中的两块盘。
[原发行资产](../releases/release_0_0_1_1024.json)
[原冻结回退验收](0a9fa011_glibc_application_release_preview.md)

## 三次冷启动

1. 用原 SDK 和原 profile 重编并打包 `selection.frozen`，结果与冻结 XPK 字节一致。把 XPK 离线装入私有发行工作盘副本，写入合成用户文件。用原发行软盘启动 `2c3876e640840ff5`，执行原 ELF，确认退出 0 和同步后 `before` 已持久化。
2. 通过新部署 kit 自带的 `xos-app` 重新构建和打包两个外部项目，核对各自的项目输入和 SDK 构建回执。普通候选从 ISO 冷启动，在独立 FAT32 工作盘运行两包。C 读取文件并验证 glibc 2.44，C++ 在容器、线程和异常场景退出 0。关机后按回执核对两个已安装 ELF，并读回原样的新盘数据。
3. 切回原 SDK，重编、检查和打包仍得到同一份冻结 XPK。用同一原软盘和同一旧盘再次冷启动，原 ELF 退出 0。同步后读回 `frozen-user-data`、`before`、`after`，两次核对已安装 ELF 的字节摘要一致。

用旧 profile 验证新包、用新 profile 向旧数据库安装新包、用新 profile 验证旧包均被拒绝。拒绝安装未生成输出镜像。旧工作盘在 glibc 阶段前后的完整 SHA-256 一致，原发布的软盘和工作盘输入复验一致。两次旧系统均从 130342 空闲页、2 个任务、0 个完成记录恢复到原值。glibc 候选从 129709 空闲页、3 个任务、1 个完成记录恢复到原值。三个客体由断网 Linux arm64 容器中的 QEMU 11.1.3 运行。

两份 glibc 重建 XPK 的字节摘要与参考包不同。比较对应 ELF 副本时，去除调试信息后的字节分别一致。实际安装与运行均使用带调试信息的新构建产物，回执记录了各自的摘要。

[回执与各项输入摘要](../reports/glibc_stock_fork_frozen_rollback_20261126/report.json)
[原系统首次启动](../reports/glibc_stock_fork_frozen_rollback_20261126/before.serial.log.gz)
[glibc 候选启动](../reports/glibc_stock_fork_frozen_rollback_20261126/glibc.serial.log.gz)
[原系统回退启动](../reports/glibc_stock_fork_frozen_rollback_20261126/after.serial.log.gz)
[原工作盘最终读回](../reports/glibc_stock_fork_frozen_rollback_20261126/preserved_user_data.txt)

## 复验入口

使用 `python3 tests/glibc_newlib_frozen_rollback_guest.py --help` 查看输入。冻结输入从发布资产和历史回退证据取得。用 SDK 初始化与参考 XPK 对应的项目，源文件位于参考 XPK 的 `payload/usr/share/<包 ID>/source/`，项目许可证位于 `payload/usr/share/licenses/<包 ID>/LICENSE`。三个项目 ID 为 `selection.frozen`、`selection.kit_c`、`selection.kit_cpp`，依次使用 C、C、C++ 模板。先用原 profile 和原 SDK 构建、检查并打包冻结项目，输出传给 `--repack-before`。运行器在全新输出目录中重建两个 glibc 项目，再切回原 SDK 重建冻结项目。ISO、SDK 与冻结输入应只读挂载，工作盘在输出目录内写入。

验收状态为 `passed_subset`，结论限定于回执中的发行输入、候选、SDK、profile、应用和合成用户文件。默认 SDK 切换、新系统组合和存量软件验收仍按各自门禁执行。
