# 0005：命令手册，终于不用猜

日期：2026-10-23（Asia/Shanghai）。负责：主 agent。状态：完成。

## 范围与结果

用户要求建立专门的使用文档，每个命令有独立帮助页，并带索引。本组新增
`docs/usage/` 手册，覆盖两套控制台：

- 内核调试控制台（`make run`）：`help`、`mem`、`alloc`、`free`、`vmtest`、
  `halt`、`pf`、`gp`、`ud`、`div`、`df`、`guo`、`joke`、`about`，共 14 页。
- 实模式练习控制台（`make run_real_mode`）：`help`、`about`、`clear`、`halt`，
  共 4 页。
- 索引 `docs/usage/index.md`：两套控制台的命令表、入口、提示符、通用输入约定、
  彩蛋开关、维护规则和文档链接。

每页包含：适用控制台、彩蛋条件、语法、行为、实际输出、失败/边界、相关命令、
实现文件与验证位置。文档描述当前实际行为，没有把未实现能力写成已支持。

## 文件

- 新增 `docs/usage/index.md` 与 `docs/usage/kernel/*.md`（14）、
  `docs/usage/real_mode/*.md`（4）。
- `README.md`、`docs/state.md`、`docs/architecture_and_boot.md` 增加手册入口。
- 没有修改内核、镜像、构建脚本或测试；构建 ID 不变（文档不参与哈希）。

## 选择与原因

- 用 Markdown 作为当前源格式：宿主可读、diff 友好、网页/GUI 可直接渲染，
  且客体尚无文件系统，不能依赖运行时 man 工具。
- 一条命令一页，避免把“索引”和“详细定义”混成一篇长文；索引只做导航和快速对照。
- 把实现位置与测试位置写进每页，方便下一 agent 改代码时同步改文档。
- 不在本组生成 man/HTML/PDF：格式选择留给用户确认，避免同时维护多套未验证产物。

## 验证

- 用 Python 检查 `docs/usage/` 内全部相对 Markdown 链接的目标存在，结果通过。
- 人工对照 `src/kernel/core/console.cpp` 与 `src/boot/x86/stage_two.asm` 的命令
  输出、提示符、行长度和错误文本；`about` 中的构建 ID 取自当前 manifest。
- 未运行新的客体测试；0004 的 `make smoke`（6 + 18）仍是当前构建的证据。
  文档变更不影响镜像与测试结果。

## 未完成与限制

- 尚未生成 man page、HTML 站点、PDF 或 CHM；Markdown 是唯一权威版本。
- 手册是宿主侧文档，客体命令不能打开它。
- 命令集合、输出文本或上限变化时，手册需要同步人工更新；目前没有自动一致性测试。

## 下一步

若用户选择 man pages（Unix 传统），可用 `mandoc`/`pandoc` 从同一份命令元数据
生成 mdoc 与 HTML，并在宿主用 `mandoc -Tlint` 验证；客体将来有文件系统后安装到
`/usr/share/man`。在格式确定前，继续以 `docs/usage/` 为准。

## 追加（0006，2026-10-23）

E03 增加内核命令 `run`，手册随之新增 `docs/usage/kernel/run.md` 并更新索引；
当前为内核 15 页、实模式 4 页加一份索引。0005 的“14 页”是加 `run` 之前的数量。
