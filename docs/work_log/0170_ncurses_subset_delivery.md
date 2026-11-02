# ncursesw 独立交付的证据绑定

现有组合 SDK 候选包含目标库、公开头、许可证材料和 xterm terminfo，但只有
`built_unverified` 回执；客体报告先前未明确绑定系统 manifest、组合包、消费者
回执与探针脚本的哈希。为支持可复核的独立交付，客体报告新增这些输入绑定及明确
profile；新增 `scripts/freeze_ncursesw_subset.py` 检查干净提交、正常 Xsh 的必需
客体检查、系统与源码、组合 SDK 树、消费者 ELF、terminfo 和串口哈希，再复制组合包、
报告及消费者到新的隔离构建目录，生成 `guest_verified_subset` 回执。

该回执只表示固定 xterm、24x80、单线程配置下指定探针通过；不提升为完整 W1/W2、
其他终端、动态尺寸、线程 profile 或许可证逐成员审计资格。脚本不修改源 SDK、系统
或测试报告。提交后须重建匹配输入、运行客体并测试冻结及不匹配拒绝；不能用旧报告
缺失的字段或仅靠宿主链接来产生该回执。
