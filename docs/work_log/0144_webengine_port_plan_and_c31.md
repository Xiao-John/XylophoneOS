# 0144 WebKit 浏览器底座计划落档与 C31 修订

2026-10-31 · 纯文档组：移植计划落档 + 宪法 v1.6。无实现、无构建、无客体测试。

## 1. 范围与产物

- 新增 [docs/plans/webengine_port.md](../plans/webengine_port.md)：WebKit 选型裁决、
  终态架构、无贷款裁决表、M0–M5 验收门、宪法依赖与资产归宿。
- [docs/xos_plan.md](../xos_plan.md) 升至 v1.6：新增 C31（用户逐字给出的
  "Build the foundation, not the illusion of completion. / 建设基础，而非制造已经完成的假象"
  及其释义），修订行记录"经用户明确确认"。
- [docs/Discipline.md](../Discipline.md) 工程尺度同步一句（遵循 C30 修订时
  宪法与 Discipline 同步的先例）。
- 不改：任何源码、ABI、登记；`state.md` 按 #36 后的分工由整合者在合并时更新。
- 交付：PR #38（`codex/webengine-plan-20261031`，基线 `ca2e372`，首提交 `12af4be`）。

## 2. 选择与原因

- 引擎三选一选 WebKit：GCC 16.2.0/CMake 与 C06 主线亲和（Chromium 官方强制 clang，
  Gecko 需先移植 Rust std）；WebKit2 三进程模型与"用户态服务 + IPC"的微内核结构同构；
  JSC 解释器-only（`ENABLE_JIT=0`）与 cairo 软件渲染都是上游官方配置，不靠私补丁。
- 候选基线 `wpewebkit-2.54.2` @ `32717fabcb9dcad9aa00a54ef1f23e41ee64e849`：2026-10-31
  经 `api.github.com/repos/WebKit/WebKit/tags` 核实；正式源锁留 M0，本文不预填哈希。
- 里程碑只给验收门不给日期：M3（网络从零）的数量级待 M0 审计后重估，不预支。
- 第 4 节"无贷款裁决表"直接落实 C31：逐条说明看似捷径的选择为何是终态。

## 3. 执行的命令与证据

- `x86_64-elf-g++ --version` → `x86_64-elf-g++ (GCC) 16.2.0`（/opt/homebrew/bin）；
  newlib `4.6.0.20260123`（scripts/user_build.py:201）。
- WebKit tags API 核实（见上）。
- 工作区：`git worktree add /tmp/xos_webengine -b codex/webengine-plan-20261031 origin/main`
  （基线 `ca2e372`；主线工作树在另一在途线上，未触碰）。
- `python3 tests/docs_consistency.py` →
  `{"status": "passed", "local_links": 539, "allocated_syscalls": 66, "history_sources": 73}`

## 4. 通过 / 失败 / 未运行

- 通过：docs_consistency（链接、ABI 登记、溯源三项）。
- 未运行（本组无实现项，非跳过冒充）：任何 WebKit 构建、M0 审计、客体测试。

## 5. 下一步

- M0 第一步按 `src/ports/aurora_browser/source_lock.json` 先例做 WebKit 正式源锁，
  落 `src/ports/webkit/source_lock.json`，哈希回填计划第 2 节；随后按
  [posix_subset 契约](../contracts/posix_subset.md) 状态词出 POSIX 缺口清单。
- 不能误认成已实现：计划落档 ≠ WebKit 可编译 ≠ XOS 有网络；M0–M5 全部未开始，
  网络能力零变化。
