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

合并提交 `0c6d512` 后重建匹配 SDK 和镜像：正常 build `4ec30ba387119e03` 的 Xsh
组合候选六组通过，权限/通道/pipe 四个限定探针通过；clock/IRQ build
`a4abfc6d52b8ffeb` 的专用客体检查通过；交接 build `2e479c275e323f73` 四组通过，
故障 build `31f76a24768dd861` 五组通过。回执分别在本工作区 `build/w1_main_0c6d512/`、
`build/w1_clock_run_0c6d512/`、`build/w1_main_{pio,irq,channel,pipe}_0c6d512/`、
`build/w1_main_handoff_0c6d512/` 和 `build/w1_main_fault_0c6d512/`。独立组合 SDK 树
SHA-256 `92a75fae3f31ff88aed584391b11b2872c5cfd1c75fc567df76ab0c8573d4985`。
Xsh 原串口文件因后续探针复用固定日志名被覆盖，只保留回执摘要，不能当作完整原始
证据；现更改测试器为每个系统构建目录保存串口，须在新提交后重跑并核对。上述检查
不覆盖完整 W1/W2，旧工作区脏文件与本地 main 尚未整合。

提交 `5f844f4` 后重新构建并运行：正常 Xsh build `5149edaf5864904a` 六组通过，
交接 build `44564ceb2663b18a` 四组通过，故障 build `cd6a65798283e278` 五组通过。
各目录的原始串口分别保存为 `ncurses_guest_serial.log`、`terminal_handoff_serial.log`、
`ncurses_guest_serial.log`，与各回执的 SHA-256 核对一致，依次为
`8960e7ef74cf225c631a203303523094d9964c4e1cb9f99cc9d2e32fca812552`、
`5366c542edb72d9131d88849b20bef9826f7d27db1aa2a2cfcd2ec7573871`、
`7a0569257b0306ff7c5b2af4135aa012f201ae036506824cabcc33c6a03e1f7a`。
回执分别位于 `build/w1_main_5f844f4/`、`build/w1_main_handoff_5f844f4/`、
`build/w1_main_fault_5f844f4/`。clock/IRQ 和负向结果仍仅绑定 `0c6d512` 的镜像。
