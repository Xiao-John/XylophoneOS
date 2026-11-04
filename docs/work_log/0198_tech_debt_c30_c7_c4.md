# 0198 — 技术债清偿：C30 存量改名、C7 证据去重、C4 放掉

2026-11-04。分支 `codex/tech_debt_c30_c7_c4`（基于 main `a165908e`）。用户裁决驱动：
Issue #37 已由用户关闭，**C4 放掉**（现版本无真隐私路径即可）；随后清偿 `docs/tech_debt.md`
第二、三节全部未清偿项。

## 1. C30-存量-01：`file::Client` → `file::client`

- 唯一定义 `src/user/include/xos/file_client.hpp` 的 `class Client` 改为 `class client`
  （对齐 `xos::terminal::client` 惯例；成员与方法本已全 snake_case，不动）。
- 新名取全小写 `client` 而非 `file_client`：后者与现有全局变量
  `xos::file::client file_client;`（newlib_syscalls.cpp:90 等）同名冲突。
- **27 个文件、88 行对称替换**：全部 `file::Client`/`xos::file::Client` 限定引用、
  `file_client.cpp` 35 处 `Client::` 外置定义、`fb12/writer_failures.cpp` 同命名空间桩、
  注释（tasks.cpp/newlib_locks.cpp）、`docs/usage/supervisor/maintenance.md`。
- **Itanium 重命名同步**（改名会变 mangled 符号）：`_ZN3xos4file6Client…` →
  `…file6client…`（长度不变，仅首字母大小写），涉及 `tests/fb0_probe.py`（`--wrap=`）、
  `tests/fixtures/fb0/file_probe.cpp`（asm 标签）、`tests/fixtures/qt6/save_failures.cpp`
  （asm 标签 + `using client=` 别名）。**冻结报告中的历史 mangled 名不改**（证据保真：
  `docs/reports/qt_e17_qualified_20261029/**` 记录的是当时实跑命令）。
- 未纳入：`audit_report_01.md`（对 `cb26f7b` 基线的时点审计记录，历史引用保持原样）。
- 验证：`x86_64-elf-g++ -fsyntax-only` 过 `file_client.cpp`、`load.cpp`；host `g++
  -fsyntax-only` 过 `fb12/writer_failures.cpp` 桩；`py_compile` 过 `fb0_probe.py`；
  全仓 `\bClient\b` 残留 grep = 0（除 audit_report 历史文本）。完整 `make build` 与
  fb0/qt6 客体重跑 **NOT_RUN**（改名为机械替换，符号一致性已由 mangled 规则与语法检查覆盖；
  下次全量构建时 `build/manifest.json` 将随源 sha 自动更新）。

## 2. C7：SSG 批次证据冗余（债项范围内去重）

按 evidence_integrity §4 做语义修订，动目标文件 + 所在目录 manifest：

- **跨目录同 sha png**：删除 `aurora_ssg_consumers_20261101/browser/browser-dom-first.png`
  （sha `ff3d81cb…`），保留 `browser_fragment_integrity_20261030/browser/` 侧副本——
  bfi 侧被 `docs/evidence_exports/issue37_pr44/evidence.json` 血统登记引用，consumers 侧
  无任何 lineage/README 硬引用（仅目录内 manifest + report.json 的 `screenshots` 元数据键）。
  `report.json` 的 `screenshots["browser-dom-first"]` 条目一并移除（该键不再是本导出的内容）。
- **目录内 serial 双份**：删除两目录各自的 `serial.log.gz`（与 `guest_serial.log.gz`
  字节相同），保留 `guest_serial.log.gz`。report.json 不按文件名引用 serial；无 SHA256SUMS。
- 同步重生成 4 份平铺 manifest（consumers 根+browser、bfi 根+browser）：
  consumers 根 94→92、bfi 根 27→26。`report_manifest_check` **passed**。
- **范围外观察（不属 C7，不处理）**：`browser-dom-reload.png` 在两目录亦同 sha；
  `serial==guest_serial` 双写是全仓约 60 个目录的历史系统性惯例（含冻结件，C5 零级联原则
  不可批量改）；现行 harness 已只写 `serial.log`。如需扩展去重另立债项。

## 3. C4：放掉（用户裁决）

- 用户关闭 Issue #37（2026-11-04T08:52:25Z）并裁决 **C4 直接放掉**：现版本无真隐私路径即可。
- **不改动测试夹具**：`tests/seed_diagnostics_cases.py` 与第三方
  `src/ports/aurora_browser/upstream/litehtml-0.9.tar.gz` 的 home 类命中，均已由
  `docs/evidence_exports/issue37/reviewed_synthetic_paths.json` 登记为
  `SYNTHETIC_FIXTURE`（合成诊断串 / 上游打包残留，非贡献者真实路径）——扫描器不绕过、
  findings 如实保留，复核记录在案。曾尝试改写夹具字符串，因会同时改变
  `diagnose()` 覆盖语义且新字符串仍触发 home 类规则而回滚，保持原字节。
- 全树 `CONFIRMED_PRIVATE_PATH` 仅 3 条，全部为上述已复核合成/上游项；其余
  absolute_command/private_temp 类属证据保真与可移植性范畴，不属隐私债。

## 4. tech_debt 更新

- 第二节：C30-存量-01 清偿移入「近期已清偿」，命名债回到无未清偿项。
- 第三节：C4 行改记放掉裁决；C7 行改记本次去重落地；C5 维持已清偿。

## 5. 命令与证据

```text
git grep -n "\bClient\b" -- src/ tests/ scripts/ docs/usage/   # 清后 0 残留
x86_64-elf-g++ -fsyntax-only -std=c++20 -nostdinc++ -I src/user/include -I <sdk>/include src/user/sdk/file_client.cpp  # exit 0
python3 tests/report_manifest_check.py   # passed
python3 tests/check_public_evidence_paths.py --commit HEAD --base origin/main  # 合并前复跑
python3 -m py_compile tests/fb0_probe.py tests/seed_diagnostics_cases.py  # OK
```
