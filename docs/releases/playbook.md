# XOS 发版 Playbook（0.0.2-1103 实操沉淀）

2026-11-04。把 0.0.2-1103 的摸索固化为可重复流程。一键入口：
`scripts/release_pipeline.sh`（本页解释每步与坑）。**不覆盖已有版本资产**；
发公开 release 前须用户明确下令。

## 0. 前提

- 宿主：`x86_64-elf-gcc`、`nasm`、`qemu-system-x86_64`、Python 3.12+。
- 仓库干净、已合入发版所需 PR；`VERSION` 已定。
- 网络仅在上传/tag 阶段需要；本地打包可离线。

## 1. 构建

```bash
make build                          # 内核+用户态+ISO → build/manifest.json
python3 scripts/build_dash.py       # dash（宿主工具 mknodes/mksyntax/mkinit 须干净 clang 预编；
                                    # 勿套 XOS CPPFLAGS；进程堆积会导致 clang 假死）
python3 scripts/build_install_iso.py  # xos-install-dash.iso + install_manifest.json
```

坑：`install_dash.py` 只装开发盘；发版用 `build_install_iso.py`。旧 `work_disk.img`
若已有 dash，import 不覆盖（FR_NO_FILE）——发版不依赖该盘。

## 2. 许可关口

```bash
python3 scripts/license_audit.py    # 必须 PASS 且 open=0（或明确带病披露）
# 若随包 Qt：packaging_verification + security_review 见
# docs/reports/qt_static_distribution_20261103/*_20261104.json（B4/B5）
```

## 3. 冻结发行目录

```bash
V=$(cat VERSION)   # 例 0.0.2-1103
R=build/releases/$V
mkdir -p "$R"
cp build/manifest.json "$R/system_manifest.json"
cp build/xos.img build/xos.iso build/xos-install-dash.iso build/install_manifest.json "$R/"
rm -rf "$R/sdk" && cp -R build/sdk "$R/sdk"
```

## 4. 打包

```bash
# cpython：必须用含 zlib 的 stage（stage_py3_b；stage_py3 可能无 zlib → ModuleNotFoundError）
# daily 与 wheel 互斥；1026/1103 实际模式 = wheel(idna) + extra-elf(工具/make/xypm)
python3 scripts/package_release.py \
  --dash-manifest .cache/xos_seed/dash/<key>/manifest.json \
  --cpython-stage .cache/xos_seed/cpython/<fp>/stage_py3_b_manifest.json \
  --wheel-package build/idna-3.20.xpk \
  --extra-elf cat=build/daily_elts_XXX/cat \
  --extra-elf make=.cache/xos_seed/make/<fp>/make \
  --extra-elf xypm=.cache/xos_seed/xypm/<fp>/project/build/xypm.elf \
  # …其余日常工具逐个 --extra-elf
```

- `package_release` 按 **manifest 文件名** 推导 stage 目录（`stage_py3_b_manifest.json`
  → `stage_py3_b/`），不要手改路径。
- 重复 guest 路径会失败：seed 的 `/usr/share/licenses/*` 与 cpython stage 的
  zlib 许可曾撞车——seed 侧不装 zlib（文本仍随 third_party_notices/Qt 资产）。
- Qt 资产独立打包（不动 `verify_sdk` 严格集）：库+头+配方+补丁+许可+源包 →
  `xylophoneos_revival_${V}_qt6_static.tar.gz`（脚本见 0203 或手工 tar）。

## 5. 冒烟与校验

```bash
python3 scripts/release_smoke.py   # 必须 11/11 → package_smoke_report.json
python3 scripts/package_release_materials.py  # sources；seed 仅许可增项时可复用 GNU correspondence
# CHECKSUMS.sha256：对 images/sdk/qt6_static/sources/manifests 逐文件 shasum -a 256
```

## 6. 发布（须用户下令）

```bash
git tag -a "v$V" -m "XylophoneOS Revival version $V" <tag_commit>
git push origin "v$V"
gh release create "v$V" --title "XylophoneOS Revival version $V" --notes "…" \
  CHECKSUMS.sha256 release_manifest.json \
  xylophoneos_revival_${V}_images.tar.gz \
  xylophoneos_revival_${V}_sdk.tar.gz \
  xylophoneos_revival_${V}_qt6_static.tar.gz \
  sources/xos-${V}-sources.tar.gz
# 回执：docs/releases/release_<V with underscores>.json（对齐 release_0_0_1_1026.json 字段）
```

- tag_commit 与 `source_manifest.source_commit` 对齐（先重打 sources 再 tag）。
- 更新 `docs/releases/next_release.md`（版本账本）与 `docs/state.md`（合并者）。

## 7. 坑速查

| 症状 | 原因/处置 |
|---|---|
| dash 卡在 mksyntax 0% CPU | 进程堆积/脏缓存；杀净、清 `.cache/xos_seed/dash/<key>`、宿主工具干净 clang 预编 |
| `ModuleNotFoundError: zlib` | 用了无 zlib 的 stage_py3 → 换 stage_py3_b |
| `daily and wheel packages use distinct profiles` | 二者互斥；用 wheel+extra-elf |
| `duplicate guest path` | seed 与 stage 许可路径撞车 |
| `source payload already exists` | 删 `build/releases/$V/sources/` 再跑 materials |
| `SDK differs from build or profile` | tree_receipt 有两套（xos_app vs sdk_receipt）；daily/xypm 用 **xos_app** 哈希 |
| git/gh SSL 中断 | 重试或 `HTTPS_PROXY=http://127.0.0.1:7897`；先探测再用 |
