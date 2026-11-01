# 0082：双Shell启动优化计划

2026-10-29。用户要求将普通命令启动优化整理为计划，分支 `codex/shell-launch-plan`，
基于FB1/FB2 `92acd02`。本组仅文档，不追加到原PR #17，不推送或创建新PR。

新增[计划书](../plans/shell_launch.md)，并在README、dash路线及state建立入口。
核对xsh实际裸命令已有一级创建能力，dash/make名称特例为三级；dash普通posix_spawn
默认不委派。明确spawn与fork/exec的权限一致性、主动削权、资源边界、旧SDK双轨兼容、
xsh历史exec语义、SL0–SL4交付及双Shell验收矩阵。当前没有实现上述新行为。

本组仅执行文档/ABI一致性与git diff空白检查；没有构建系统、运行客体或修改冻结报告。
后续从SL0核对远程主线及PR #17合入状态开始，冻结专项契约和兼容表再实施。
