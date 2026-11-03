# 宿主终端证据进入受限交付

2026-11-03。W2 计划要求记录声明的宿主终端，已有 GNU Screen 探针和客体运行结果；
但旧的 `freeze_ncursesw_subset.py` 只复制客体串口与目标输入，未把 Screen 报告、
画面硬拷贝和外层 PTY 数据纳入交付，不能仅靠此冻结树复核宿主检查。

本次冻结要求 Screen 的受限 profile、检查项、客体报告与串口哈希及宿主探针脚本
哈希一致，校验硬拷贝和外层 PTY 的哈希与所要求内容；将三份材料复制到 evidence，
复制后再次核对。Screen 版本和二进制哈希随报告保留。这不是证明物理字体、所有
xterm 控制序列或键盘映射，也不将许可和完整 W1/W2 提升为已验收。提交后须基于
当前源码重新构建系统并取得绑定的客体和 Screen 结果，验证冻结成功，且对缺失或
篡改 Screen 材料的副本拒绝冻结；旧冻结树保持原有边界，不得改绑。

提交 `e93f630` 后重新构建系统（build ID `76f558e4da02bae2`），在校验过来源输入
的组合 SDK 与消费者上运行 QEMU 和 Screen，客体为 `passed_probe`，Screen 为
`passed_subset`。冻结树 `build/w2_screen_evidence_frozen_e93f630/` 的状态为
`guest_verified_subset`，包含 208 个文件，树 SHA-256
`c1ac94c38a0b7969a569985494e1bb250351a82b6f58abcba154d4fac424ab4f`；新增三份宿主
材料已包含在树中。单独复制系统证据后，删除硬拷贝或篡改 PTY 数据都会在创建冻结
输出前被拒绝。源客体及 Screen 回执位于 `build/w2_screen_evidence_system_e93f630/`。
