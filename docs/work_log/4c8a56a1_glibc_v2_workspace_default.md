# 4c8a56a1 · glibc v2 应用默认与冻结 newlib 回退

从主线 `4c8a56a1` 重建普通 ISO `99e0cafb79a74825`，启用首个外部程序启动前的
演示任务回收选项。签名来源的统一 C/C++ v2 SDK、冻结 newlib SDK、v0.0.1-1024
原发行启动软盘、原工作盘和历史回退工作盘按各自回执绑定，只读挂载。构建、宿主
选择和三次冷启动使用断网 Linux arm64 容器及 QEMU 11.1.3。10 项 ISO 许可材料
检查通过。[冻结输入与原回退](4ffa226d_glibc_stock_fork_frozen_rollback.md)

| 冷启顺序 | 实测结果 |
| --- | --- |
| v2 默认 | 通过 `xos_sdk.py setup` 注册两套 SDK，缺省选择 glibc。使用未显式传 SDK/profile 的应用命令重建 C/C++ XPK，实跑 FAT 读取、glibc 2.44 版本、C++ 线程、容器和异常，回到 `129709 / 3 / 1`。 |
| 冻结 newlib | 临时移走私有 v2 kit 副本后，状态查询拒绝继续，显式 `use newlib` 成功。已冻结项目重新生成逐字节相同的 XPK。原版启动软盘 `2c3876e640840ff5` 执行原 ELF、读回旧文件并追加标记，回到 `130342 / 2 / 0`。 |
| 恢复 v2 | 复原 kit 后恢复原选择文件字节，两套工作盘在选择时保持原摘要。普通 ISO 冷启后两个新应用再次运行，核对包所有权、文件摘要和用户数据。 |

两个方向均拒绝错 profile 的包或已登记数据库。未登记原工作盘副本拒绝
`list`、`install` 和 `repo-install`，盘摘要不变且无事务输出盘。原始旧盘始终
保留原字节。此结果适用于应用与宿主包工具的默认选择。完整发行默认及历史 SDK 的
归档退役仍以最终发行组合为准。
[三次冷启与资产摘要](../reports/glibc_v2_workspace_default_20261127/manifest.json)

## 重跑

使用原验收入口及原发行输入，将 `UNIFIED_KIT` 指向本轮 v2 kit。普通系统先从当前
准确源码树用 `scripts/build.py --quiet-demos-on-launch --output-dir "$SYSTEM"` 重建。
用全新输出运行 `tests/glibc_sdk_default_guest.py`。若在容器中运行 Git worktree，
须同时提供只读 Git 管理目录，使回执能记录实际分支的提交。
[参数与历史对应关系](50e9a5a4_glibc_sdk_default.md#验收方法)
