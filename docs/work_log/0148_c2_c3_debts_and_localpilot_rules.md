# 0148 技术债 C2+C3 核销与 localpilot 隔离条款移除

2026-10-31 · 分支 `codex/c2_c3_debts_20261031`（基线 `a1315c1`，即 #53 合并后主线）。
本组两项债并行调查（两个 subagent 分头执行、主线集成者复核），外加用户中途指令。

## 1. 范围与产物

- **C2（PR #21 四遗留）**：
  - `.gitattributes`：查实"3/138"= **138 份冻结证据只被字节冻结规则覆盖了 3 份**
    （`modern_apps_20261029/evidence_index.json` 恰 138 条）；补
    `docs/reports/modern_apps_20261029/** -text` 整目录覆盖，实测 `git check-attr`
    138/138 `text: unset`，目录外不受影响。
  - `scripts/modern_apps_matrix.py`：35 格验收列原为写死字面量 → 改为**从冻结回执
    读真值**（sdk/native/guest `report.json`），缺回执直接 `SystemExit` 拒绝编造；
    30/35 格与冻结 CSV 逐字节一致，5 格改从回执取真值（含原漏写的 mprotect FAILED）；
    新增 `--output` 与拒绝覆盖冻结件的守卫。冻结 CSV 未动。
  - `tests/modern_apps_guest.py`：`compatibility_status` 原按探针名写死 → 改为从客体
    真实退出码+标记推导（application/missing_api/capability 三类角色），报告 schema 不变；
    实测从冻结客体日志复现冻结报告状态 10/10。
  - `licenses/components.json` pypdf：`source` 由项目首页改为**钉版本+sha256 的
    files.pythonhosted 直链**（哈希取自冻结回执 `python_dependencies.json`，非联网下载），
    与 `version`/回执三方一致断言通过。
- **C3（PR #19 四项核销）**：
  1. 历史回退卡死 bug：**已修可核销**（0096/`da77f66`：`bool navigate` 失败不提交历史）；
     #39 后的验证空档本组补跑——负向 18/18（含历史回退回归）、交互 10/10。
  2. CSS 拒绝文案：0096 未定、原为误标 → **本组修**：`view.hpp` 按异常 `what()` 映射
     `Stylesheet rejected`/`Stylesheet import quota exceeded`，`content.hpp` 去掉误称的
     "budget"，套件期望与契约同步。
  3. virtio 适配器未入仓：查实适配器副本从未提交（冻结件只剩其哈希
     `5cf2b9a3…`+原作者私有树路径）→ **本组补 `--backend vbe|virtio`** 到正式 runner
     （照 `virtio_gpu_acceptance.py` 模式），virtio 轮 10/10 实跑
     （`[display] backend=virtio-gpu-2d`、476 帧）。
  4. 契约未实测措辞：0096 段落已过时（把已跑说成未跑）且漏标 → **本组改**：如实引用
     g3/本组实跑，并新增 "Not measured here"（16 条历史上限、4 tab 上限均未实测）。
  - 附带修复：`view.hpp` `log_anchor()` 首屏布局前打印过期坐标致 PS/2 锚点首轮失败
     → 每次 `relayout()` 后重报（改前基线同路径失败，与文案改动无关）。
- **localpilot 隔离条款移除**（用户 2026-10-31 指示：localpilot/ 已移出主工作区）：
  `docs/xos_plan.md` 底线条款删除（**宪法 v1.7** 修订行登记）、`docs/Discipline.md`
  两处、`.gitignore` 的 `/localpilot/`、`docs/state.md` 与 `README.md` 各一处。
  保留：法律/事实性提及（NOTICE、licensing、project_overview、audit_report_01、
  mit_legacy）、功能性脚本开关（`--localpilot` 探针参数）与构建输出安全守卫
  （`build_utf8_newlib.py`/`derive_cpp_runtime.py` 禁止输出落入该目录——防误写的代码
  守卫，非纪律表述）。
- 本组的 subagent 初稿工作记录命名为 0113（与尚未合并线的 0113–0143 潜在撞号），
  已并入本文件后删除，避免 C5 类撞号。
- **许可审计门的既有失败（本组发现并修复）**：`scripts/license_audit.py` 在主线
  即红——#33 新增的 `src/kernel/platform/pc/interrupts.cpp` 用了
  `MIT AND Apache-2.0` 头，不满足"新源自研源文件须含 `SPDX-License-Identifier: Apache-2.0`"
  子串规则（同批 `clock.cpp` 即纯 Apache-2.0；该文件不在 legacy 清单）。改为纯
  `Apache-2.0`（C10），审计现 `PASS: 7 license materials`。冻结件
  `net_clock_irq_split_20261030` 仍绑定改动前字节（旧报告不改绑；差异仅首行许可声明，
  无行为变化，`git diff` 一行可证）。

## 2. 选择与原因

- 两处"硬编码结果"一律改为**从回执/真实观测推导，查不到就报错**，绝不回填猜测值（C31）。
- "3/138"按实证重新解释（覆盖不足而非缺 3 个），修复以实测 `check-attr` 为准。
- pypdf 哈希取自本仓冻结回执（离线可信链），不新造来源。
- C3 四项先核销后修复：能跑的都跑了（VBE/virtio 双后端），不以"0096 写过"代替实测。
- 本地提交纪律文件的删除动作按用户原话限于"表述"：删除规则条款，不删历史证据与法律范围句。

## 3. 执行的命令与证据（集成者复跑/核对）

- 客体套件（本组 subagent 实跑，证据 `build/browser_hostcheck/`，可重建非冻结）：
  `interactive` VBE **10/10**、`interactive --backend virtio` **10/10**、
  `negative` **18/18**、`aurora_browser_no_display.py` **3/3**；
  ELF `16ce4acd…`、镜像 `8a7eb736…`（=0146 分支镜像）、QEMU 11.1.2 TCG。
  构建：`src/ports/aurora_browser/build.py` + 本组既有的 widgets2/host 工具/SDK。
- 静态门（集成者复跑）：`git check-attr` 138/138；matrix 35 格回执解析+缺回执守卫；
  guest 推导 10/10 复现冻结状态；`py_compile` ×3；`python -m json.tool`；
  pypdf 三方一致断言；`docs_consistency`、`abi_doc_consistency`、`git diff --check`。
- `license_audit`：components.json 变更后需重建 SDK 副本再审计（`scripts/build.py` →
  `license_audit.py`），结果见下方"通过/未运行"。
- 环境备忘：浏览器套件像素读取需 Pillow ≥12.3（`Image.get_flattened_data`），
  本机 venv 为 11.3，实跑经 `PYTHONPATH` 引用宿主已有 Pillow 12.3（只读 import，
  未改动他项目）；PyPI 直连本网络不可达。

## 4. 通过 / 失败 / 未运行

- 通过：§3 全部门与四套浏览器套件（含 virtio 轮）。
- 失败（过程记录，未改判）：`interactive` 首轮 `real_ps2_anchor_click` 因锚点坐标
  过期失败——属既有诊断打印缺陷，修复（`log_anchor` 重报）后两后端各 10/10。
- 未运行（如实）：matrix **完整再生成**（需私有 localpilot 检出与
  `build/modern_apps/sources`，本机无——脚本原必填项，非本次新增）；pypdf **真实
  下载校验**（pypi 不通）；`--case lifecycle`；峰值内存/长压；契约新标的
  16 条历史/4 tab 上限。

## 5. 下一步

- 用户 review/合并本 PR；合并后 C1（已并 #53）、C2、C3 一并移入"已清偿"。
- 已知后手：matrix 完整再生成与 pypdf 下载校验待具备条件时补做（不阻塞核销，
  生成器与钉版本本身已静态验证）；`licenses/components.json` 同文件的 `defusedxml`
  同样未钉版本、`modifications` 字段存在 QuickJS 文案复制残留——非本债条目，
  已在账本登记候选。
- 不能误认成已实现：localpilot 条款移除 ≠ 任何移植完成；C3 的 lifecycle/峰值
  仍未跑。
