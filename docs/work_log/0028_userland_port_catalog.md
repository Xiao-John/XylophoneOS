# 0028：用户态工具移植菜单

2026-10-25。用户要求本线不干扰正在进行的 dash 移植，只负责列出可移植软件、
确定候选与首批边界，供项目所有者按兴趣选择。本文档规划不构成任何工具已开工。

## 完成内容

- 新增 `docs/userland_port_catalog.md`，按现有 XOS 真实能力整理编辑器、基础命令、
  正则/文本工具、归档压缩、构建工具、Lua、CPython和后续终端工具。
- 首个全屏编辑器建议 Kilo-XOS K0，而非直接移植 nano/Vim；首批使用 port-local
  固定尺寸 VT100 后端，只承诺 ASCII、打开/保存/搜索/光标和失败保护。
- 基础命令建议从 MIT sbase 逐个移植，U0 从 `cat/cp/wc/cmp` 等独立 ELF 开始；
  不选择 BusyBox 作为第一批，不使用符号链接或 multicall 假定。
- 构建工具首选条件成熟后的 Samurai `-j1` 子集；当前文件时间字段为零，因此
  不把 Make/Ninja 能启动误认为增量构建正确。
- CPython保留独立既有规划，本文只明确PY0–PY4边界，不开始实现；Lua是可跳过的
  轻量兴趣支线，不成为CPython或构建前置。

## 核对与证据边界

只读核对当前 SDK/newlib、用户态适配和文档：目标头含 `regex.h`/`termios.h`，但
目标 `libc.a` 未导出 `regcomp/regexec/regfree/regerror`，且当前没有 `tcgetattr`、
`tcsetattr`、通用 `ioctl` 实现；`gettimeofday` 返回 ENOSYS，`stat` 时间字段为零。
这些是候选分批依据，不是新实现。

上游资料只用于选型：sbase README/源码与MIT许可证、Kilo源码/BSD条款、nano官方
README、Samurai README/许可证、Lua官方发布页、CPython官方交叉构建说明。实际开工
仍须重新冻结版本/提交、下载原包、计算摘要并逐文件核对许可证。

本组没有修改 dash、supervisor、loader、libc、SDK、内核、测试或许可证清单；
没有构建或启动 QEMU，所有功能状态均为 `not_run`。没有读取或修改 `localpilot/`。

## 下一步

由项目所有者按兴趣选择一个菜单项。选定后先在 `state.md` 登记与现有任务不重叠的
文件范围，再建立独立 cache/build 输出和该工具的客体 gate。当前共享 `state.md`
与整合文档由 0027 工作占用，本组没有覆盖其进行中内容。
