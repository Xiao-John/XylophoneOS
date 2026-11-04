# 0203 — 0.0.2-1103 打包与 release_smoke 11/11

2026-11-04。D 步：冻结目录 → package_release（cpython stage + idna wheel +
extra-elfs）→ release_smoke **11/11 PASS** → CHECKSUMS。

## 打包装配（对齐 1026 模式）

| 输入 | 选择与原因 |
|---|---|
| cpython stage | `11c39c52…/stage_py3_b`（含 **zlib**；`ad85d843` 验收树无 zlib 不可用） |
| idna | `--wheel-package build/idna-3.20.xpk`（profile 已追加准入当前 build/SDK） |
| 日常工具 | **不用 daily-package**（与 wheel 互斥）；14 个 ELF 逐个 `--extra-elf` |
| make | `build_make.py` 产物 `b2e3c1a0…` extra-elf |
| xypm | 1026 同款缓存 ELF `ddd13972…`（`7606b907…/xypm.elf`）extra-elf |
| Qt | 独立资产 `…_qt6_static.tar.gz`（80.7MB：17 静态库+头+配方+10 补丁+37 文本+qtbase 源包） |

## 脚本修复（本轮入库）

1. `package_release.py`：cpython stage 目录按 manifest 名推导（支持 `stage_py3_b`）。
2. `package_release_materials.py`：seed 变更若**仅为** `/usr/share/licenses/*` 增项
   （剥离后 sha == 1024 记录值）则复用 GNU correspondence，否则仍硬失败。
3. `prepare_gcc_seed.py`：移除 seed 侧 `zlib/LICENSE` 装盘项（与 cpython stage 撞
   guest 路径；文本仍经 stage/third_party_notices/Qt 资产随包）。
4. profiles：`daily_c3_candidate` 与 `static_single_b2_v1` 追加当前 build/SDK 准入。

## 结果

- `release_smoke`：**11/11 passed**（fresh_work_disk_no_dash、install ISO launcher、
  native/sdk C+CPP、dash_c3、make、python_py3（zlib+idna）、xypm_query、ISO dash 全哈希）。
- 资产（`build/releases/0.0.2-1103/`）：images 90.3MB、sdk 9.1MB、qt6_static 80.7MB、
  sources 357.7MB + `CHECKSUMS.sha256`。
- 发行说明：`docs/releases/0.0.2-1103.md`。

## 待办（本轮后）

- 上传资产 + tag `v0.0.2-1103` + GitHub release + 回执 JSON（**待用户下令**）。
- **发版文档与脚本化**（用户 2026-11-04 指示）：沉淀 `docs/releases/playbook.md` +
  `scripts/release_pipeline.sh`，消除每次摸索。
