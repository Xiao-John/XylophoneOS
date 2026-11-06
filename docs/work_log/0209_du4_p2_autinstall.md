# 0209 — DU4：type5 工具 ELF、staged 列表与 P2 自动安装

2026-11-05。DU4 收尾特性片：容器可携带 bootstrap 工具 ELF，supervisor 在首启
抽取后经真实维护租约自动 `xypm install`，marker 保证幂等。

## 变更

| 文件 | 内容 |
|---|---|
| `scripts/xos_bundle.py` | `TYPE_TOOL=5`；build/parse 校验 type1/type5 为 ELF |
| `docs/contracts/xos_bundle_v1.md` | type5 `tool_elf` 行；ELF 魔数规则含 type5 |
| `src/user/include/xos/file_ui.hpp` | `staged_count` / `staged_path` / `bundle_marker_present` / `bundle_marker_write` |
| `src/user/services/file_ui.cpp` | type5 → `/usr/bin/<name>`；type2/3/4 → incoming 并记入 staged 列表；marker 文件 `/var/cache/xypm/du4_bundle.installed` |
| `src/user/programs/supervisor.cpp` | `maintenance_run` 改为返回 `bool`；`ui::init()` 后若 staged>0 且无 marker，逐个 `maintenance_run("xypm","install",path)`，全部成功写 marker |

## 行为

- 首启：抽取 → 自动安装 → `[files] bundle packages installed` + marker。
- 安装未全成：`install incomplete; will retry next boot`，不写 marker，下次重试。
- 已有 marker：跳过自动安装（幂等）；用户仍可手动 `maint-run`。
- 无 xypm 二进制时自动安装失败但不影响抽取（E2E 回归 6/6 仍过）。

## 验证（build `540225e9d97f2b1c`）

```text
python3 -m unittest tests.test_xos_bundle    # 16/16 OK
tests/iso_bundle_install.py                  # 6/6
tests/iso_bundle_reject.py                   # 11/11（宿主4拒+guest坏sha+无成功路径）
tests/iso_bundle_reboot.py                   # 8/8（幂等+marker+dash）
tests/iso_bundle_daily.py                    # 7/7（3成员/11MB 容量）
tests/iso_bundle_p2_install.py               # 9/9（demo quiet→auto-install→xypm list/info）
tests/iso_dash_install.py                    # 4/4 裸 ELF 回归
check_public_evidence_paths                  # PUBLIC_READY
```

## 排障补充

- 自动安装过早会撞 `process_error_busy`（demo 未清场）→ 挪到欢迎语后并先 `demo quiet`。
- seed xypm 0.1/0.2 **无 install**；P2 测试用可安装 xypm（`recover (maintenance only)` 标记），
  必要时经 `.cache/xos_seed/xypm_sdk/single_b2_v1` 现编 0.3。
- 二次启动时 demo 输出会拆开 `members=2` 字面量 → 测试改为全量输出断言。
