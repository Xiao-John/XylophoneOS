# ncurses 分支与当前主线整合

在独立工作区将 ncurses 分支 `347834c` 与 `origin/main` 的 `dc33b43` 整合，
未改其他工作区。主线已将 PIC/PIT 移到 PC 平台并以统一 clock 管理时间；本次将
IRQ4 mask、unmask、EOI 迁入平台中断机制，保持应答不推进时钟，并将 W1 的截止时间
比较改用同一 `clock::monotonic_ns()`。保留主线 clock/IRQ 探针与 W1 两个 supervisor
探针的构建开关和 manifest 绑定；全局 state 采用主线快照规则，细节留各工作记录。

公开路径检查发现本分支新增工作记录含机器临时目录；已替换为明确标注的
`${XOS_SCRATCH}` 模板，历史结果及哈希不变。上游补丁原始末尾空行由属性保留，未
修改补丁。`python3 scripts/build.py --output-dir build/w1_main_integration_v2` 通过，
build ID `4ec30ba387119e03`；文档/ABI 一致性、许可证材料检查、公开路径检查及
证据路径测试通过。首次组合构建因三个 W1 截止时间仍引用旧时钟函数失败，已改为
统一时钟并重建。该构建在本记录之前，不作为新提交客体资格。

所有旧客体证据仍绑定各自原提交；须在合并提交后重建 SDK、系统和 ncurses 组合，
重跑终端、权限、clock/IRQ 及适用主线回归，再核对剩余 W1/W2、local main 与 PR。
本次只完成冲突处理和构建，未声称 W1/W2 已完成或更改本地 main。
