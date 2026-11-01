# 0145 技术债 B1 清偿：15 个自研 CamelCase 类名改 snake_case

2026-10-31 · 分支 `codex/c30_rename_b1_20261031`（基线 `c47b355`，即 #38 合并后主线）。

## 1. 范围与产物

- 清偿 `docs/tech_debt.md`（该文件按指示已加入 `.gitignore`，本地维护）条目 **B1**：
  15 个自研类名 `BackingStore`/`Brand`/`Button`/`Canvas`/`Editor`/`Fonts`/
  `GuiDispatcher`/`Integration`/`NoteHighlight`/`Panel`/`Pointer`/`Screen`/
  `Style`/`Window`/`XosWakeGate` → snake_case，20 个文件、117 处旧标识符、
  范围内零残留。
- 两个提交：`ac8160d`（纯标识符改名，字节可证）+ `c938bf6`（改名引发的
  上游名冲突修复，32 行，全部是限定修饰、无二次改名）。
- 验收工件 `docs/reports/c30_rename_b1_20261031/`：`rename_map.json`、
  `delta_proof.json`（20/20 文件替换恒等）、`fixes.json`、`checks.json`、`README.md`。
- `.gitignore` 追加 `docs/tech_debt.md`（同 STATE_L 模式：活工作记忆、永不入提交）。
- 未动：B2 两个 QPA 上游强制名（`QEventDispatcherXos`/`QXosIntegrationPlugin`，
  待用户裁决）、任何内核/ABI/登记、`state.md`。

## 2. 选择与原因

- 改名按 C30；上游限定名保留是 C30 豁免（`QPalette::Window/Button` 未动，
  记录在 `rename_map.json.upstream_qualified_kept`）。
- 改名与冲突修复分两提交：证明"改名本身标识符恒等、修复逐行有因"，
  延续 0112 的 rename_map/delta_proof/fixes 三件套方法。
- 与继承上游方法的同名冲突用限定修饰解决（`QPlatformWindow::window()`、
  `::window*`、成员处 `aurora::`），不为迁就实现二次起名——类名 `window`
  保持蛇形，符合 C30 字面与 C31 底座取向。

## 3. 执行的命令与证据（本机 macOS arm64）

- 环境：Apple clang 21.0.0；homebrew qtbase 6.12.0（含 private 头与
  libexec/moc）；SDK `build/releases/0.0.1-1026/…_sdk/include` 与
  `build/threading_sdk/include` 经 `-idirafter` 引入（正序会毒化宿主 libc，
  实测记录）。
- 语法门：`clang++ -fsyntax-only -std=c++17 <I 列表>` 全量扫 14 个改名依赖
  TU/夹具 → **14/14 PASS**（含 `qpa/qxos.cpp`，moc 占位说明见 checks.json NOT_RUN）。
- 功能门：`clang++ … ssg_diff_integrity.cpp ssg.cpp -framework QtCore/QtGui/QtWidgets`
  构建并运行 → **13/13 PASS, failures=0**（含 #29 新增的 `stale_generation_since_resets`）。
- mock 探针：`python3 tests/mock_semantic_agent.py` 正例 rc=0 出提案、`{}` rc=1、
  70000 字节输入 `snapshot budget` 拒绝。
- `python3 tests/docs_consistency.py` → passed（543/66/73）；
  `python3 tests/abi_doc_consistency.py` → PASS（16 项不变）；`git diff --check` → 干净。
- `tests/aurora_scope_audit.py --base c47b355` → `kernel_source_changes: []`，
  唯一违规即被改名的 `src/ports/qt6/qpa/qxos.cpp` 本身（该审计保护的是
  "应用任务不碰 QPA"，本任务按 C30 正是 QPA 文件改名，语境记入 checks.json CONTEXT）。
- 证明生成：python 脚本对 20 文件做 `\bold\b`→new 替换（theme.cpp 记录例外）
  与 `git show ac8160d` 逐字节比对 → `all_files_identifier_only: true`。

## 4. 通过 / 失败 / 未运行

- 通过：上述 7 项（见 checks.json PASSED）。
- 未运行（如实登记，非跳过）：客体 QEMU 套件（目标 Qt 构建树/镜像不在本机，
  与 0112 同限制；冻结客体证据经 delta_proof 传递延展，不改绑）；
  `qxos.moc` 宿主再生成（moc 6.12 拒绝 IID 标识符形式、目标 moc 6.8.3 接受，
  空占位仅过语法门）；`qmutex_xos.cpp` 宿主检查（Qt 6.12 私有头漂移，该文件
  与主线逐字节一致且不依赖任何被改名头文件，不属本债范围）。

## 5. 下一步

- 用户 review/合并 PR；合并后把 `docs/tech_debt.md` 的 B1 移入"已清偿"表。
- B2（2 个 QPA 上游强制名）待用户裁决；下一项债由用户指定。
- 不能误认成已实现：客体套件未重跑不等于已再验收；语法/宿主运行不冒充客体资格。
