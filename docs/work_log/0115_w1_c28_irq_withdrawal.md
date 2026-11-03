# 0115：撤回违反 C28 的新增内核串口数据通路

2026-10-30。按 0114 的架构审查，从 W1 分支撤回新增内核 UART IRQ4 处理、接收
队列和硬件 overrun 计数；恢复 main 已有的引导/调试串口与 PIC/中断路径，不以
其 C26 例外冒充用户态设备驱动。sys54 保留显式管道截止时间，但 console 等待
恢复 would-block。既有等待客体探针包含未实现的 console 场景，不能作为通过证据。

sys80 暂时对 supervisor claim 返回 unsupported：用户态 UART 和非内核终端取消
策略尚未建立，不能启用先前依赖内核 Escape 抢读例外的权限模型。通用 IPC 与管道
等待代码保留但仍未验；SDK manifest 显式标记 claim_unsupported。历史 0084、0085、
0089 和 0092 记录原时点，不改写为现状态。

`python3 scripts/build.py --output-dir build/w1_c28_irq_revert_final_20261030` 成功，
提交前 build ID `c48aa1ecef01ec6c`。未运行 guest；未证明串口、输入、W1 或 W2。
下一步按 C20 冻结窄范围 PIO 授权、IRQ 通知/应答和撤权，实施用户态 UART 驱动、
终端服务、模式恢复与 ncursesw；全部相关更改提交后验收。
