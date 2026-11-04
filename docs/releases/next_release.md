# 已发布版本与下一次发行准备

2026-11-04 更新。**0.0.1-1026 已发布**；**0.0.2-1103 本地打包完成、
release_smoke 11/11**，资产见 `build/releases/0.0.2-1103/`（上传/tag 见本页
发行记录与回执）。不改写旧资产或验收结果。

**发版配方与脚本化**：完整逐步流程见 [playbook](playbook.md) 与
`scripts/release_pipeline.sh`（2026-11-04 起）；本页保留版本账本与冻结回执。

## 0.0.1-1026 冻结回执

- 标签`v0.0.1-1026`、源码提交`db5b46cf36b57a602946a370269563f9c8dd212f`。
- build`7a4668477d7323de`，release smoke 11/11，资源[130272,2,0]；
  7份许可材料检查通过，newlib成员级追溯仍开放。
- 新工作盘不预装dash；install ISO携带dash并在首次启动安装，已存在文件不覆盖。
- images/SDK/source/校验表/manifest均已上传，来源与哈希见
  [发布回执](release_0_0_1_1026.json)及[0050过程记录](../history/delivery_audit.md#log-0050_release_candidate)。
- 容量probe kernel和附加trailer的dash仅用于0047验收，不是发行载荷。

| 已发布资产 | SHA256 |
|---|---|
| CHECKSUMS.sha256 | `e65457ba52f40d23ff602ebf3e53479a614c51a3c95f8e580d4c607392f15848` |
| release_manifest.json | `6d73a563b9ae7089e324e381dc912223a5103897d88230ff79948159cb8051d6` |
| xos-0.0.1-1026-sources.tar.gz | `3f1ead9867ca567a3a1e14edd59fcbca42d238b9159c115fc96b9e7727930657` |
| xylophoneos_revival_0.0.1-1026_images.tar.gz | `8dcc344f5126c2128896684455116d288d8331ca08f5d16118bf72abf7d131a8` |
| xylophoneos_revival_0.0.1-1026_sdk.tar.gz | `a09e6157fc5409152e2646484eb03cec5509433558734fb291d161c53365b4a1` |

## 0.0.2-1103 打包状态（2026-11-04）

- 源码定格 `6fe330ce`；build `8356e45af316fc93`；dash `5ddda601…`；install ISO 绑定。
- **release_smoke 11/11 passed**（`package_smoke_report.json`）。
- 资产（含 **Qt 静态交付物**，用户指令）：

| 资产 | SHA256（前16） | 大小 |
|---|---|---|
| `xylophoneos_revival_0.0.2-1103_images.tar.gz` | `1de27573ca7119b7…` | 90.3 MB |
| `xylophoneos_revival_0.0.2-1103_sdk.tar.gz` | `929d6070f016f831…` | 9.1 MB |
| `xylophoneos_revival_0.0.2-1103_qt6_static.tar.gz` | `744a5260cfab63cd…` | 80.7 MB |
| `sources/xos-0.0.2-1103-sources.tar.gz` | `a103a48145432406…` | 357.7 MB |
| `CHECKSUMS.sha256` / `release_manifest.json` | 见目录内文件 | — |

- 打包装配要点（详见 0203 与 playbook）：cpython `stage_py3_b`（须含 zlib）、
  idna 走 **wheel**、日常工具/make/xypm 走 **extra-elf**（daily 与 wheel 互斥）、
  Qt 独立资产；`license_audit` 0 open；B4/B5 门槛已执行。

## 下一次发行时的工作（流程已脚本化）

逐步命令见 [playbook](playbook.md)；一键入口 `scripts/release_pipeline.sh`。要点：

1. 定版本号 → `make build` + `build_dash.py` + `build_install_iso.py`。
2. 许可关口：`license_audit`（0 open）+ Qt B4/B5（若随包 Qt）。
3. 冻结发行目录（`system_manifest.json`/`xos.*`/`sdk/`/`install_manifest.json`）。
4. `package_release.py`（stage_py3_b + wheel + extra-elfs + Qt 资产另打）。
5. `release_smoke.py` 须 11/11；生成 `CHECKSUMS.sha256`。
6. `package_release_materials.py`（GNU correspondence；仅许可增项 seed 可复用）。
7. 上传资产 + tag + GitHub release + 回执 JSON（`release_<version>.json`）。

旧 1026 回执缺新字段仍保留历史原样；材料检查通过不代表成员级法律审计完成。
