# wait-any 验收状态与输入身份审计

## 范围与修改

基于 PR #161 的本地提交 `a3a1654`，处理评审
`4694695071`、`4694695118`、`4694695133`。本组只修改验收代码；
`sys_process_wait`、SDK/wire ABI 与进程实现保持原行为。

1. 客体 `unchanged` 逐字段比较 `process_status` 的七个字段，补上
   `outcome`、`address`、`instruction`，避免失败调用改写这三项时漏检；
   不依赖结构体填充字节。
2. 内核 wait 宿主提取器读取一次 `tasks.cpp` 字节；代码提取与
   `source_sha256` 都来自这个快照。随后源路径发生变化时，报告仍准确
   标识实际编译的原始代码。
3. 客体 runner 首次冻结经过 `bind_system` 核验的 manifest 原始字节、
   build ID、source SHA、ISO SHA 与 SDK manifest SHA；临近启动前及
   全部客体结束后再次核验并逐项比较。系统目录即使换成另一份内部自洽的
   产物，也会报错，无法写入 `passed`。

同时将 sys20 的 wait-any 说明移至 ABI 表前的正文，保持登记表“定义来源”
列的既有格式。首次文档检查发现原 PR 在该列追加说明后，严格解析器无法
识别编号 20；仅调整说明位置后重新检查。

## 实际验证

```sh
python3 tests/kernel_process_wait_race_test.py --output build/review_host
python3 tests/kernel_process_wait_race_test.py --sanitize --output build/review_sanitized_host
python3 tests/process_wait_acceptance_host.py --output build/review_identity_final
python3 scripts/verify_evidence_index.py docs/reports/process_wait_review_20261125/manifest.json
```

内核 wait 宿主 **8/8**、ASan/UBSan **8/8** 通过；LeakSanitizer
关闭。验收绑定宿主 **8/8** 通过，覆盖：

- 不变系统的正常控制；另一份自洽的 build ID、ISO、SDK，以及仅 manifest
  原始字节变化的四种拒绝；首次绑定期间切换 manifest 的拒绝。
- 编译客体的真实 `sentinel/unchanged` 定义，独立改变七个字段均被识别，
  未改动的控制保持通过。
- 在内核代码提取完成后、编译器启动时改变私有 `tasks.cpp` 副本；
  真实 wait 宿主仍跑完 8 项，报告摘要仍对应它实际编译的原始快照。

身份控制使用有完整摘要关系的合成系统目录；这些控制没有执行占位 ISO。
内核宿主运行真实提取代码，仅模拟特权页表、调度及无关设备清理边界。

| 原始报告 | SHA-256 |
|---|---|
| `build/review_host/report.json` | `5226b7813fc734eb42c585a11ebb9887f480b8a55a984cbc4f5fd55c7306e68f` |
| `build/review_sanitized_host/report.json` | `4392062ca11d15f3695a872ba2d7b585071ddfdef9789e28cae08cd732495133` |
| `build/review_identity_final/report.json` | `72d76e6e26de70552df0be23851c291ada14aaead4367e4987b7372cf80d8296` |

公开的 [派生报告目录](../reports/process_wait_review_20261125/summary.json)
只把本机源码目录替换为 `${XOS_SOURCE_ROOT}`，原始摘要在其中单独保留。
目录根 `manifest.json` 平铺绑定全部八个叶子，原件仍在上述 `build/` 路径。

## 客体缺口与交接

本修订的 **27 项真实客体尚未运行**。组合里程碑正在构建一份包含
G3 文件、进程、终端及 C++ 运行库的新系统，计划合入本修订后复用该
新系统进行 wait-any 客体验收。执行入口如下：

```sh
python3 scripts/build.py --output-dir build/wait_review_system
python3 tests/process_wait_any_guest.py --system build/wait_review_system \
  --output build/wait_review_guest --repeat 3
```

要在生成系统的同一源码工作树执行 runner。原 PR 的 27 项通过结果保持
原来的源/镜像绑定；新客体结果完成后补独立证据提交。
