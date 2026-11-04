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

提交 `f5349b4ce3585bdf23ccf6e85b734da627223f65` 后重建系统、用已核验输入的
组合 SDK 重新链接消费者并运行正常 Xsh 客体，`passed_probe`；首次冻结结果
`guest_verified_subset`，树 SHA-256
`6df50da0d883a048d204bd4ce471fd29dff3ae78c9c090ab7be7218283b8d9e3`。单独复制并修改
消费者 ELF 后冻结被拒绝，提示 artifact 不匹配。该次系统 build ID
`f0bfbcad84220a0b`，manifest SHA-256
`64d0a1eaffdc4051ea06e83459260552c1806cbf2219448b7744ccbc562fdf44`，串口 SHA-256
`8af22f3e063e14f467e6f2765858d43c8dbae31e4a168b37baec850fe93bddc5`；报告及首次
冻结分别位于 `build/w2_freeze_system_f5349b4/` 和 `build/w2_frozen_subset_f5349b4/`。

复核发现首次冻结未一并携带底层 SDK、目标库和 terminfo 的输入回执，也未携带系统
镜像及终端 ELF。冻结工具现要求并复制这些材料，逐项验证其哈希；更改提交后须按
新命令重建、重新运行客体并再次测试冻结与拒绝，不能把首次冻结当作新版本结果。

提交 `28d8c7563e226e5e53a7b39c28b9d6283a237924` 后重建正常 Xsh 系统、重新链接
消费者并核验现有 SDK 源码输入；客体 `passed_probe`，新版冻结成功，包含底层回执、
系统镜像、终端 ELF、消费者与串口。结果 `guest_verified_subset`，树 SHA-256
`db7c6f28a34d19190999ab28f1ac76799ce0d7022d9f49c772eb265f374b641c`，位于
`build/w2_frozen_subset_28d8c75/`。系统 build ID `b2334a2f12a28c80`，manifest SHA-256
`216a8d508b7945747680e1c9754a52f90b6a4a43afee9fbef10b1b0ec4a9a59b`，镜像 SHA-256
`9a96839c012488b2aaa36c77c5221f199347be09e3b07e2ffc1bd9767541ac12`，组合 SDK 树
SHA-256 `038491cd8cefcc77551b681b3954e20983d979f7d1d32a4df7bf982bf0fd27d0`，
串口 SHA-256 `b5b20a3b57ffb17f8133221d40ee147c81514cb86165e75cdaf2b808f2b63e65`。
修改消费者 ELF、修改 terminfo 回执及传入旧提交客体报告均被拒绝。回执仍不声称
完整 W1/W2；后续源码或系统组合变化需重新运行并绑定。
