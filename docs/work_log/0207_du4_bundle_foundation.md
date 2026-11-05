# 0207 — DU4 前期：XOSBND1 容器契约、生成器与客体识别

2026-11-05。DU4（[通用 ISO 安装载荷](../plans/daily_utilities_iso_payload.md)）前期交付；
完整安装与验收未做。

## 1. 勘查基线（实测）

- `spawn_buffer`/`image_buffer` = **131072**（128 KiB）；`iso_payload_max_bytes` = **33554432**（32 MiB）。
- 候选成员体积：dash.runtime 277064、xypm.xpk 1382400、daily_utils.xpk 11458560、idna.xpk 368640；合计 ≈ **12.9 MiB** ≪ 32 MiB。
- `sys_boot_payload(off,buf,len)` 已支持分块拷贝；`spawn_file`/`spawn_reader` 已支持按句柄流式装载——128 KiB 不是装载整包的阻塞点。
- `install_boot_dash()`（file_ui）旧逻辑把整个 ISO 载荷当 dash ELF 写入 `/usr/bin/dash`。

## 2. 交付

| 项 | 位置 |
|---|---|
| 容器契约冻结 | [docs/contracts/xos_bundle_v1.md](../contracts/xos_bundle_v1.md)（64B 头 + 64B 成员表 + 名称区 + 4 对齐数据区；type1 dash 必恰 1；32 MiB/16 成员上限） |
| 宿主生成器/校验器 | `scripts/xos_bundle.py`（build/verify，拒绝规则按契约 §4） |
| 单元测试 | `tests/test_xos_bundle.py` **13/13 OK**（往返、缺 dash、重复 daily、坏 magic/version/total/hash、截断、reserved、非 ELF、真 xpk 魔数） |
| 客体识别 | `file_ui.cpp` `install_boot_dash`：读前 8 字节，`XOSBND1\0` 则打印拒绝并 return，**不再把容器写成 dash**；非容器 ELF 走旧路径 |

## 3. 未做（DU4 正文）

- 容器写入 ISO 并随 `build_install_iso` 出货；supervisor 解包/校验/分发成员；
- 经 P2 门禁安装 xypm/daily 包、空盘/重启/冲突/失败恢复矩阵；
- `spawn_buffer` 相关的 loader 分块方案（现有 `spawn_file` 流式路径优先，契约已写明）。

## 4. 验证

```text
python3 -m unittest tests.test_xos_bundle   # 13/13 OK
git grep XOSBND1 -- src/user/services/file_ui.cpp  # guard present
```

未运行：QEMU 客体 ISO 安装（DU4 正文）；`make build` 全量（file_ui 变更待下次构建门禁）。
