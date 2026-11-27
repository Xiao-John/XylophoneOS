# 645ba017 · 普通镜像和 glibc v2 安装候选复验

从干净主线 `645ba017` 分别重建普通预设和显式 glibc 安装候选。
普通镜像 `0a591c6ed6985dbe` 使用锁定的 lwIP 2.2.1，实际运行
`make smoke`。79 项常规客体检查、10 项许可材料检查和 ABI 表通过。

安装候选 `0d4b152cf6c9fdf9` 由断网的 Linux arm64 构建容器使用已核验
的 glibc v2 应用 SDK 和锁定 sbase 源码生成。候选同时产出普通 ISO 和
安装 ISO，安装 bundle 包含对应的 Dash、daily XPK 与 xypm。容器的
QEMU 11.1.3 首次运行完整 smoke 时触发内核测试的 11.1.2 版本门。
独立安装专项使用同一容器工具，从新输出目录执行：

```sh
python3 scripts/build_candidate.py --output "$XOS_CANDIDATE" \
  --glibc-app-kit "$XOS_APP_KIT" --glibc-daily-source "$XOS_SBASE" --installer-guest
```

安装器的五项检查通过，其中包含首次执行外部 ELF。空盘自动安装日用包，
重启后核对 13 项工具、26 个已登记文件。客体卸载后核对两处用户数据、事务
清理、资源及 33 个确定输出文件。构建脚本冻结两张 ISO、SDK 及安装清单，并
核对安装和生命周期回执的输入摘要。

安装候选产物冻结后，在宿主以锁定的 QEMU 11.1.2 运行 `make -o build smoke`
并以 `python3 tests/docs_consistency.py` 核对 ABI。常规检查 79 项、许可材料
10 项及 ABI 全部通过。测试使用的系统镜像和 SDK 清单与冻结副本摘要一致。
候选脚本自身的常规 smoke 字段仍保留原始的未运行状态，独立复跑证据登记在本页回执。

[文件清单](../reports/next_stage_645ba017_20261127/manifest.json) ·
[源码与产物绑定](../reports/next_stage_645ba017_20261127/binding.json) ·
[安装器回执](../reports/next_stage_645ba017_20261127/installer.json) ·
[日用包回执](../reports/next_stage_645ba017_20261127/stock.json)

本轮未跑整套发行资产、升级中断及历史 newlib 盘回退，发行资格沿用各自的验收门。
主线后续合入的 Qt Quick v2 与发行组件源码材料各有专项回执。
[发行门](../releases/glibc_default_gate.md) ·
[Qt Quick v2](659b4dc2_qt_quick_unified_v2.md) ·
[发行组件源码](9c747f60_glibc_v2_component_sources.md)
