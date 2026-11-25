# 3eac9c17 — 拒绝退出所有者降级清理窗口

## 范围与评审

2026-11-25，回应 PR #156 review comment `4694186902`。
基线 `0d3b4bf3d05e894417a358c0214bdd74c6511be4`。
sys51 mode 1 的所有者原可再调用 mode 0 清除 deadline 并停止 peers，导致后续
应用/stdio 锁等待失去强制终止期限。补丁在 mode 0 处理的首个状态检查中拒绝
任何已经存在的 cleanup window，返回 `process_error_state`，不改变所有权、
deadline、超时状态及 peer 状态。首次 legacy mode 0 和其所有者重入保持原行为。
接口语义同步 [threading 契约](../contracts/threading.md#有界进程清理窗口sys51-mode-1)。

## 检查与证据进度

`tests/kernel_exit_cleanup_gate_test.py` 从实际 `tasks.cpp` 提取完整 sys51 分支，
以确定性时间、用户复制和 reaper stand-in 验证 mode 1→mode 0 序列，包含所有者、
其他线程、重复 mode 1、legacy mode 0 首次/重入及全部相关状态保持。
旧代码实际失败：`cleanup owner downgraded to stop-peers`；修复后通过。
日志分别为 `build/exit_review_old_gate.log` 和 `build/exit_review_fixed_gate.log`。

真实客体 `exit_protocol.c` 的 ABI 用例新增同一 owner 在 peer 尚存和 peer 已退出
时的 mode 0 拒绝；随后仍须在原一秒 deadline 发布 125，保持先前注册的状态。
另增 legacy mode 0 首次/重入客体，使用 `_exit(46)` 收尾。退出专项重建和实际
客体结果在后续验证提交追加；本代码 checkpoint 的客体状态为待运行。

本变更仅涉及内核 gate、契约和测试；已有 glibc SDK 的移植源码与构建输入不变，
后续可复用原 SDK，并为新内核/测试重新构建独立系统镜像。历史 61 项证据原件保留。

## 完成的客体验证

代码修复为 `e307da021e754a8022eb1532292fb19d30beff5e`，runner 的标记顺序修正
为 `61960d70efa5a02244b3599b5f5ab061d9424e56`。重新构建的系统 build ID 为
`92762946085dbae6`，复用原正式 SDK `active_exit_verified_sdk`，客体验收前后
校验全部 184 项 SDK 输入和 685 项 sysroot 产物，并核对新镜像源码及产物。

退出专项 **39/39 PASS**（13 场景 × 3 轮）。正常 return/exit 的回调、完整 flush、
文件内容、并发退出、递归退出、worker 退出、quick_exit、owner fault/abandon
继续通过。每一项结束后资源精确回到 **129719 free pages / 3 tasks / 1 completion**。

| 定向场景 | 三轮实际结果 |
|---|---|
| owner 在 peer 存活和已自然退出后调用 mode 0 | 均返回 -6，原一秒 deadline 最终发布 125；宿主观测 1.445 / 1.530 / 1.525 秒 |
| legacy mode 0 首次与同 owner 重入 | 均成功，最终退出 46；资源回归 |
| worker 永久持 stdout 锁 | 回调先运行，flush 受阻；30 秒原生期限后退出 127，宿主观测 30.627 / 31.037 / 30.588 秒 |

宿主确定性 sys51 gate 回归和现有 process wait/reaper 回归均通过。原有全套
61 项冻结证据保持；本次针对 gate 修复运行退出专项，没有重跑完整 files/threads
套件及跨分支组合镜像。SMP、真实硬件和长压力仍由后续专项补充。

首次客体运行在 `g3_exit_abi` 断言处失败：输出已包含拒绝标记、正确原 deadline
超时和退出 125，但 runner 把两条预期标记写成相反顺序。修正 runner 后，直接
重用旧镜像的尝试被源码快照检查拒绝；随后新建系统和客体输出目录，获得上述
39 项结果。失败原件保留在 `build/exit_review_guest`、
`build/exit_review_guest_verified` 及对应 `.log`，不把失败轮次计入通过数。

| 文件 | SHA-256 |
|---|---|
| `build/exit_review_verified_system/manifest.json` | `c2fae789cb633a26e1dd8967f68725a066c8ada2db1d7b0722ed744d3a05b472` |
| `build/exit_review_verified_system/xos-install.iso` | `65669a3920262b1eb4f642dbe54c490dd0863b256951714a33ff10524502c3a1` |
| `build/exit_review_qualified_guest/report.json` | `4443e7f2a5ac04ac61c09796c8154625615acefe638c6099c34175e9e571c52e` |
| `build/exit_review_qualified_guest/serial.log` | `6afce9e7df92cbb59beacf70c9e8cac390740ba002abc5ef45bc7133b90bcd46` |

## 索引复现评审

PR #156 comment `4694186895` 指出原记录最后核验索引的命令缺少生成步骤。
[原工作记录](8bfdcae1_glibc_active_process_exit.md#复现) 现补充完整 Python 生成
命令，以排他创建写入新的 `active_exit_reproduced_index.json`，保留历史索引。
按该代码实际执行，生成 **1406** 项并核验 **1406/1406 PASS**；摘要为
`acc9e8511ea8b20a04c5a7d48b5defc173f8aecb8c86ca6a144fe8d50409213e`。
生成日志及核验结果保留在 `build/exit_review_index_generation.log` 与
`build/exit_review_index_generation_verification.json`。文件数随复现产物变化，
生成命令输出本次实际值。

提交前文档检查通过（1054 个本地链接、78 个 syscall 登记、73 项 history
来源），公开路径检查 8/8 `PUBLIC_READY`，新生成的 1406 项原验收索引再次
全量匹配。`git diff --check` 通过。

## 复现命令

复用已完成且摘要匹配的原正式 SDK；`XOS_SDK_RUN` 指向 preview 工具入口。
以下系统和客体输出目录必须是新目录：

```sh
python3 tests/kernel_exit_cleanup_gate_test.py
python3 tests/kernel_process_wait_race_test.py
"$XOS_SDK_RUN" python3 scripts/build.py --output-dir build/exit_review_verified_system
"$XOS_SDK_RUN" python3 tests/glibc_static_guest.py \
  --system-build build/exit_review_verified_system \
  --glibc-build build/active_exit_verified_sdk \
  --output build/exit_review_qualified_guest --suite exit --repetitions 3
python3 tests/docs_consistency.py --output-dir build/exit_review_docs
python3 tests/check_public_evidence_paths.py --index --base 0d3b4bf3d05e894417a358c0214bdd74c6511be4
```

索引生成和核验按上一节链接中的完整步骤执行；它核验原完整验收的实际材料，
本次 gate 复测的关键摘要单列如上。
