# 0204 — 0.0.2-1103 发布与发版流程沉淀

2026-11-04。完成用户指令「1 发布 + 2 文档脚本化」。

## 1. 发布

- **Tag** `v0.0.2-1103` → `071330f3`（= `source_manifest.source_commit`，先重打 sources 对齐）。
- **GitHub Release**：https://github.com/Xiao-John/XylophoneOS/releases/tag/v0.0.2-1103
- **6 资产**：CHECKSUMS.sha256、release_manifest.json、images(90.3M)、sdk(9.1M)、
  **qt6_static(80.7M)**、sources(357.7M)。
- **回执**：`docs/releases/release_0_0_2_1103.json`（tag/source/build/smoke/许可门槛/资产哈希）。
- 系统 build `8356e45af316fc93`；release_smoke 11/11；license_audit 0 open。
- 过程：PR #74（D 步补入 main）、#75（next_release.md）；PR #73 仅含 A/B 门禁。

## 2. 文档与脚本化

- `docs/releases/playbook.md`：七步流程 + 坑速查（stage_py3_b/zlib、wheel↔extra-elf、
  双 tree_receipt、dash 宿主工具假死等）。
- `scripts/release_pipeline.sh`：`build|gates|freeze|package|smoke|materials|checksums|status`
  分阶段执行；**publish 不自动**（须用户下令）。
- `docs/releases/next_release.md`：版本账本更新 + 流程指针。
- `docs/usage/userland/`：用户态开发上手两页（getting_started / in_guest_build）+ 索引
  （子代理交付，命令均实测）。
- `docs/releases/0.0.2-1103.md`：发行说明（GUI 成就先讲 + Qt 随包）。

## 验证

```text
gh release view v0.0.2-1103  → 6 assets, published 2026-11-04T14:59:27Z
bash -n scripts/release_pipeline.sh → OK
release_smoke 11/11（打包时）
```
