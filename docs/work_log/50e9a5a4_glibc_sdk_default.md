# 50e9a5a4 · 应用 SDK 默认选择与冻结回退

工作区用 `scripts/xos_sdk.py setup` 注册已验证的 glibc C/C++ kit 及 v0.0.1-1024 冻结 newlib SDK。应用构建和宿主包工具共用已选绑定。选择失效时拒绝继续；原 SDK 可用时，`use newlib` 即可回到原工程、profile 和专用工作盘。`use glibc` 恢复初始选择。两次切换只更新选择文件。

工作盘必须先用显式 profile 在专用盘上登记，查询、离线包事务和仓库事务均在已有锁内检查数据库。旧盘、未登记盘和错误 profile 的 XPK/数据库分别验证，旧用户数据继续由原系统读写。冻结资产保留历史来源和原字节。
[使用命令与工作盘契约](../contracts/xypm_sdk_profiles.md#工作区的应用-sdk-默认选择)
[原发行回退](4ffa226d_glibc_stock_fork_frozen_rollback.md)

## 验收方法

在隔离 Linux arm64 环境使用同一套交叉工具，从 `50e9a5a4` 重建普通系统与 glibc 安装候选。新系统验收从普通 ISO 启动，旧系统依照原版 v0.0.1-1024 从发行软盘启动。第一次预跑在启动前发现此前代表应用镜像绑定了旧 `scripts/xypm.py`，保持原回执和镜像后重建。宿主 profile 45 项和 P3 仓库 50 项通过。

```sh
candidate=build/candidates/workspace-sdk-default
python3 scripts/build_candidate.py --output "$candidate" --glibc-app-kit "$UNIFIED_KIT" \
  --glibc-daily-source "$SBASE"
python3 tests/glibc_sdk_default_guest.py --kit "$UNIFIED_KIT" --system "$candidate/system" \
  --newlib-sdk "$FROZEN_NEWLIB_SDK" --frozen-report "$PREVIOUS_ROLLBACK_REPORT" \
  --frozen-disk "$PREVIOUS_ROLLBACK_DISK" --original-unmarked "$PUBLISHED_WORK_DISK" \
  --frozen-boot "$PUBLISHED_BOOT_IMG" --frozen-package "$FROZEN_XPK" \
  --frozen-project "$FROZEN_PROJECT" --output build/default-selection/guest
python3 tests/xypm_sdk_profile_host.py
python3 tests/package_p3_repository.py
```

`FROZEN_PROJECT` 是原 1024 SDK 构建冻存 XPK 的工作项目。可用 XPK 内附的源文件和许可证按原 ID 重建。在运行器之外保持两个已注册的 SDK、旧发行软盘、旧工作盘、历史回执和 XPK 为只读输入。运行器为旧系统和 glibc 分别创建盘副本，保留各阶段的实际回执。

## 三次冷启动

| 选择和系统 | 客体结果 |
| --- | --- |
| 初始 glibc · `3a17018acf8ff034` | 外部 C 与 C++ 样例按统一 profile 重建、核包、安装和运行。C 从 FAT 读取用户数据并确认 glibc 2.44，C++ 通过容器、线程和异常。两次退出均恢复至 `129709 / 3 / 1`。 |
| 冻结 newlib · `2c3876e640840ff5` | 临时移走 glibc kit 的私有副本后，状态检查拒绝继续，显式回退成功。原项目重打包的 XPK 与冻结包逐字节一致。原系统启动后执行原 ELF，读回并保留旧用户文本，追加测试标记，退出恢复至 `130342 / 2 / 0`。 |
| 恢复 glibc · `3a17018acf8ff034` | 复原 kit 后恢复原选择文件的字节，两个程序再次启动并正常退出。停机后重新验证两个已安装 XPK，用户文件逐字节一致。 |

两次切换均比对两张选定工作盘的全盘摘要。未登记的原发行盘副本拒绝 `list`、`install` 和 `repo-install`，事务未生成候选盘，输入与拒绝后的盘逐字节一致。已有数据库与 XPK 在两个方向均拒绝错 profile。运行器分别保留两次 glibc 启动、一次历史 newlib 启动与原发行盘摘要。QEMU 11.1.3 三次均从冷启动开始，采用断网 Linux arm64 容器。
[验收回执](../reports/glibc_application_sdk_default_20261127/selection.json)
[系统与安装镜像构建摘要](../reports/glibc_application_sdk_default_20261127/candidate.json)
[证据清单](../reports/glibc_application_sdk_default_20261127/manifest.json)

## 验收范围

工作区选择的边界是应用工具与宿主包工具。发行仍需针对最终软件清单提供每个入选包的许可和源码/重链接材料，合入最终系统后复验对应生命周期。#317 的统一 profile 代表矩阵覆盖 dash、GNU Make、xypm 和日用工具。CPython、Qt Quick、Mobius 和 ClarkE 此前的各自候选证据继续绑定各原 profile。newlib 对照和冻结回退遵循独立盘规则。
[代表应用矩阵](d6ead81f_glibc_profile.md)
[发行默认门](../plans/glibc_port_scout.md#从加固期走向默认切换的门)
