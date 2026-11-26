# 1ea5a358 · G4 xypm 自升级恢复与发行预览复验

从主线 `1ea5a358` 重建普通系统 `1658dee772d30bea`。使用已有上游签名核验和完整库树绑定的 glibc 2.44 / GCC 16.2 C/C++ SDK，按 `xos-x86_64-glibc-stock-fork-v1` 构建正常 `xos.xypm` 和测试专用故障版本。两份包的回执绑定相同的 SDK 与 profile，系统内置恢复器由同一源码树构建。

## 客体自升级

断网 Linux arm64 容器中运行 QEMU 11.1.3。用真实 xypm 自升级，定位旧的 `/usr/bin/xypm` 被移除后的第 150 个事务检查点。在独立初始盘副本重放，从该点同步并退出，停机核对旧可执行文件已不在磁盘而事务日志仍在。重启后从 ISO 启动内置恢复器，恢复原包、数据库和用户文件，再重启并成功重试正常升级。各轮检查资源统计均回到 129806 空闲页、2 个任务、0 个完成记录。

同一 glibc profile 内由 `0.4.0-0` 的故障版换成同版本正常包。该演练覆盖升级事务替换、可重放中断和恢复。断电及扇区撕裂仍待验收。冻结 newlib 隔离盘回退见 [PR #296](https://github.com/Xiao-John/XylophoneOS/pull/296)。
[客体证据](../reports/glibc_xypm_self_upgrade_g4_20261126/manifest.json)

```sh
python3 scripts/build.py --quiet-demos-on-launch
python3 scripts/build_xypm.py --sdk "$GLIBC_KIT/sdk" --profile "$GLIBC_KIT/profile.json" > "$NORMAL"
python3 scripts/build_xypm.py --sdk "$GLIBC_KIT/sdk" --profile "$GLIBC_KIT/profile.json" --fault-injection > "$FAULT"
python3 tests/package_p2_self_upgrade.py --system build --build "$NORMAL" --fault-build "$FAULT" \
  --profile "$GLIBC_KIT/profile.json" --output "$GUEST_REPORT"
```

## 本地发行预览

对同一系统 ISO 和同一 C/C++ SDK 运行 `application-preview assemble` 与独立 `verify`，同时保留固定的 v0.0.1-1024 newlib 归档及其 profile。两个命令返回同一回执。该系统的 10 项登记许可材料检查通过，开放项为 0。程序集的状态字段仍为 `guest_qualification: not_run`，xypm 自升级的客体结果由上面的独立门禁记录。
[预览核验](../reports/glibc_xypm_self_upgrade_g4_20261126/preview_verified.json)
[发行手册](../releases/playbook.md#glibc-应用-sdk-发布预览)

## 代表性端口和发行材料待验项

| 项目 | 已有证据与剩余门 |
| --- | --- |
| dash、日用工具、GNU Make、外部 C/C++ | stock fork 候选已有实际组合启动。最终镜像变化时，以最终 SDK 和候选清单复验。 [应用矩阵](cc71c241_glibc_stock_apps.md) |
| CPython | `build_cpython.py` 已提供显式 glibc 入口，核心、标准库和原生包生命周期已通过独立 CPython profile。代表性复验仍需用选定 stock fork SDK 和最终普通盘从源码重建 XPK，测试既有磁盘标准库场景及包升级。Pillow 等扩展有独立门。 [包生命周期](53a73e7c_glibc_cpython_xpk.md) |
| Qt Quick | 可搬移 kit 已通过外部软件渲染示例，Mobius Qt Widgets 有独立启动和包证据。冻结 stock fork SDK 与现有 Qt 产物绑定应再核对。Qt Declarative、Qt Shader Tools 的完整分发源、静态库成员级条目及实际重链接仍待验收。 [Qt Quick](870aabad_qt_quick_relocatable_kit.md) [Mobius](f38242fd_mobius_glibc_xpk_lifecycle.md) |
| 源码对应与重链接 | `package_glibc_sdk.py` 随 SDK 交付构建 manifest 及来源核验材料。`package_release_materials.py` 仍以旧 GNU seed 对应素材和已锁定 CPython 依赖为输入。正式 glibc 发行包须附该候选对应的原始源码、修改和可重现的重链接输入，并对一份选定应用实际执行替换重链接及客体复验。 [SDK 打包器](../../scripts/package_glibc_sdk.py) [发行材料入口](../../scripts/package_release_materials.py) |

本次资格为 `passed_subset`。默认 SDK 切换和 newlib 退役仍按 G4 及最终组合门执行。
