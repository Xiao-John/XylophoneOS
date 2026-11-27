# 9dd3de65 · glibc 发行候选合装 daily、CPython 与 IDNA

以主线 `1086f41b` 和 #327 实测分支 `8d6446e3` 为基线。交付前核对
主线合入 #327 的 `85e29a61` 两者树相同。本轮使用锁定的同一 glibc C/C++
应用 SDK，保留原 CPython 3.14.9-1（静态 zlib 1.3.2）及 IDNA 3.20 XPK。
daily 随被选中的实际安装候选重新构建。签名 SDK 和三个包源只读挂载。

## 实现

发行入口 `scripts/release_pipeline.sh package` 增加显式 glibc 候选方式。
与旧入口复用 XPK profile、归属、摘要与盘事务验证。新方式逐一绑定普通 ISO、
安装 ISO、实际安装容器成员和 installer/stock 客体回执，并确认受测 xypm、
dash、daily 与选中 SDK/profile 相同；即使旧 `verified_system_builds` 为空，
仍能依据具体已验收工件准入。历史 daily 和 wheel 单包入口继续走原装配设置。

同 profile 的 daily、CPython 与可选的 IDNA 由宿主事务安装到新 FAT 工作盘，
逐文件核验 xypm 归属。失败即撤销本次新目录；输入盘、包和 SDK 保持原字节。
初次重开比对发现把发行 receipt 写入 SDK 根目录会改变冻结 kit 摘要。
正式装配仅把副本放在镜像归档，SDK 归档保留原样。历史 Python fixture 曾因
传入 `ZipInfo` 而生成 stored ZIP；共享冒烟现在指定并读取 DEFLATE 方法。

## 复现

```bash
python3 scripts/build_candidate.py --output "$CANDIDATE" --glibc-app-kit "$KIT" \
  --glibc-daily-source "$SBASE" --installer-guest
scripts/release_pipeline.sh package --release-dir "$RELEASE" \
  --glibc-candidate "$CANDIDATE" --glibc-app-kit "$KIT" \
  --cpython-package "$CPYTHON_XPK" --wheel-package "$IDNA_XPK"
scripts/release_pipeline.sh smoke --glibc-release "$RELEASE" --output "$SMOKE" \
  --foreign-package "$FROZEN_PROFILE_IDNA_XPK"
python3 tests/glibc_release_preflight.py --candidate "$CANDIDATE" --kit "$KIT" \
  --cpython "$CPYTHON_XPK" --wheel "$IDNA_XPK" --foreign-wheel "$FROZEN_PROFILE_IDNA_XPK" \
  --other-daily "$OTHER_DAILY" --old-python "$CPYTHON_WITHOUT_ZLIB" --output "$PREFLIGHT"
```

宿主为断网 Linux arm64，目标为 x86-64，QEMU 使用 TCG。每天工具的来源从
锁定 sbase 实物挂载。发行目录在 `build/releases/` 下单独创建；客体写盘是
发布盘的字节一致独立副本。新的候选、历史对照候选与各自的装配、客体回执分开。

## 客体结果

| 候选 | 源码 | 镜像 build ID | 安装与冷启 | 卸载后的读回 |
| --- | --- | --- | --- | --- |
| 冻结 #317 | `aece9965` | `b210965441f899cc` | 安装 ISO 的原生 daily 安装确认，普通 ISO 冷启，57 个受管文件 | daily 与 IDNA 卸载，保留 15 个 CPython 受管文件和原用户数据 |
| 本轮重建 | `9dd3de65` | `73601d7ff1c68866` | 安装 ISO 的原生 daily 安装确认，普通 ISO 冷启，57 个受管文件 | daily 与 IDNA 卸载，保留 15 个 CPython 受管文件和原用户数据 |

两套镜像在安装和冷启后均通过线程、JSON、gzip、DEFLATE ZIP 和 IDNA。原生
xypm 拒绝异 profile XPK，恢复命令确认无事务。卸载后再次运行 CPython，
gzip 可用且 IDNA 已退出模块搜索。两套运行的安装资源计数均回到
`125923/2/0`，普通镜像计数均回到 `129806/2/0`。重新打开两组分发归档
逐文件核对，镜像归档各 6 项，应用 SDK 归档各 1781 项。另验证省略 wheel
的装配保留 41 个受管文件，断言范围限于装配和所有权检查。

发布默认配方继续由发行验收表约束，最终资产仍须满足 GNU Seed、静态重链接
材料和产品组合的各自要求。
[素材绑定和实际串口](../reports/glibc_release_package_composition_20261127/manifest.json) ·
[默认发行验收表](../releases/glibc_default_gate.md)
