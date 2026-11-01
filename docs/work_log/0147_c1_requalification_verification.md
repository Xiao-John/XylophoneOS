# 0147 技术债 C1 核销：#29 修复③④的客体再验收确认

2026-10-31 · 分支 `codex/c1_requal_verify_20261031`（基线 `8ec0489`，即 #52 合并后主线）。

## 1. 范围与产物

- 核销 `docs/tech_debt.md` 条目 **C1**：#29 两个行为变化修复
  （③ `now_ns` 纳秒粒度/进程内起点，`aurora/ssg.cpp`；④ 按钮自定义调色板
  不被覆盖，`aurora/style.cpp`）与新增用例②的 QEMU 套件欠账。
- 本组为**证据核销**，不改任何源码：C6（PR #52，已合并）在其四套件上
  正是跑在含 ③④ 修复的改名后基线上，0112 登记的欠账套件清单与 C6 实跑
  清单逐一对应；另补一项纳秒粒度直接探针（见 §3）。
- 产物：本工作记录；`tech_debt.md`（本地账本）C1 行核销。

## 2. 覆盖对照（债项 → 实跑证据）

| C1 欠账（0112 登记） | C6 实跑（`c6_guest_requal_20261031`） | 结果 |
|---|---|---|
| `aurora_standard_button_guest`（④ 按钮配色） | 检查名即 `explicit_palette`/`palette_painted`，断言与修复语义一致 | PASSED 3/3 |
| `aurora_platform_guest --case render` | 实机截屏渲染 | PASSED 13/13（11 截屏） |
| `aurora_platform_guest --case semantic`（③ 所在 ssg 流） | 31 项客机原生断言，元数据含 `observedMonotonicNs` 交付路径 | PASSED 5/5 |
| `ssg_diff_guest`（② 新增 stale_generation 用例） | 含 `stale_generation_since_resets` | PASSED 13/13 |
| blur | `aurora_blur_cases` 宿主实跑 | 396 向量 + 6 拒绝 PASS |

基线含修复的依据：C6 分支基于合并了 #39/#52 的主线，③④ 的源文件
（`ssg.cpp`/`style.cpp`）自 #29 起除 C30 标识符改名外无行为改动
（`aurora_c30_rename_b1_20261031` 的 delta_proof 20/20 字节恒等可传递）。

## 3. ③ 纳秒粒度直接探针（宿主，临时程序未入库）

对当前树 `aurora/scene_stream::publish` 连发两次，读返回帧
`observedMonotonicNs`：

- 命令：`clang++ -std=c++17 -I src/ports/qt6/aurora … now_ns_probe.cpp ssg.cpp
  -framework QtCore -framework QtGui -framework QtWidgets && ./now_ns_probe`
- 输出：`NOW_NS_PROBE grew=1 sub_ms=1 delta_ns=20583` → 两次发布差
  20,583 ns、亚毫秒位非零，证实现行实现为纳秒粒度（修复前 ms 粒度必为
  10^6 整数倍）。宿主 Qt 6.12 下实测；客机语义由上表 semantic 套件覆盖。

## 4. 通过 / 失败 / 未运行

- 通过：上表四套件 + blur + 本组探针；`docs_consistency`、
  `abi_doc_consistency`、`git diff --check` 于提交前复跑。
- 失败：无（本组不重跑套件——证据引用已合并的 C6 报告，避免重复资格）。
- 未运行：`aurora_platform_guest --case dash`（与 C6 相同，不属本债范围）。

## 5. 下一步

- 用户 review/合并本 PR；合并后把 C1 移入"已清偿"。
- 下一项由用户指定（C2–C5 或 A 系列）。
- 不能误认成已实现：本组未新增任何功能；探针为一次性验证，非入库测试门。
