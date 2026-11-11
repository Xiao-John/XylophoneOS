# 0208 — DU4：容器入 ISO、客体抽取与 E2E

2026-11-05。DU4 第二片：宿主 `build_install_iso --member` 产出 XOSBND1 载荷，
客体 `file_ui` 校验并抽取 dash + XPK，端到端测试通过。P2 自动安装仍未做。

## 交付

| 项 | 说明 |
|---|---|
| `scripts/build_install_iso.py` | 新增可重复 `--member TYPE:NAME=PATH`（2=xypm 3=daily 4=aux；dash 恒为 type1）；组装 `xos_boot_bundle.bin` 作为 ISO 的 `DASH.ELF`；`install_manifest` 增加 `boot_bundle`（容器 sha + 成员表） |
| `src/user/services/file_ui.cpp` | `install_boot_payload`：识别 `XOSBND1\0` → 校验头/表/角色/不重叠 → 流式读 `sys_boot_payload` + `sha256` 核验 → dash 写 `/usr/bin/dash`、XPK 写 `/var/cache/xypm/incoming/<name>`；**拒绝**把容器当裸 ELF 写入。裸 ELF 旧路径保留（`[files] dash installed bytes=` 字符串不变） |
| `tests/iso_bundle_install.py` | 新 E2E：组包 ISO → 空盘启动 → processed members=2 → dash/xpk 落盘 → `ls incoming` → `dash -i` 回显 |

## 排障记录

1. 首跑失败：改 `file_ui` 后未重建镜像 → 整容器被旧逻辑写成 dash（645908 B）。
2. 重建后 `sha256 mismatch`：抽取时把成员内偏移当**容器绝对偏移**读 →
   `install_member_file` 增加 `base`（= `data_off`），`read_payload(base+offset)`。
3. `-Werror=shadow`、缺 `fault_sha256.hpp` include：已修。

## 验证（build `9c4403d2f4bc5482`）

```text
python3 -m unittest tests.test_xos_bundle     # 13/13 OK
python3 tests/iso_bundle_install.py           # passed: bundle-processed, dash-from-bundle,
                                              # xpk-staged, incoming-listed, dash-stat, dash-runs
python3 tests/iso_dash_install.py             # passed（裸 ELF 回归 4 checks）
check_public_evidence_paths                   # PUBLIC_READY 0 findings
```

## 未做

- supervisor 自动 `xypm install`（现为 staged + 手动/测试 `maint-run`）；
- 重复启动/坏容器/磁盘满客体矩阵；daily.xpk（11MB）进载荷的容量组合验收。
