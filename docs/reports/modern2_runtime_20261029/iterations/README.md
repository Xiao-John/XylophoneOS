# 原始运行与证据修正

所有原始报告按其原字节保留；本目录不是最终资格。

- `initial_guest`：最初未主动quiet boot demos的11项运行，资源基线为free130235/tasks6/completions0。大量demo串口输出保留。
- `pre_review_guest`：build e885d9593cc29d63的11项运行，已显式quiet，资源基线为free130279/tasks2/completions0。其Promise脚本只给出排队标记，模块输出只有Promise对象，不能作为异步完成证据。
- `pre_review_sources`：上述实际runner、builder、JS源快照；旧builder会复用existing patched source，旧receipt没有runner SHA。保留该缺口，不把新哈希写进旧receipt。实际编译runner内容与PR21源一致，此处保存其原字节。
- `completion_check_guest`：新runner保存求值结果，排空jobs后检查Promise fulfilled和结果值；11项重新运行通过。随后再增加pending/rejection/异步断言三个负控制，重新构建系统并运行，最终14项回执在上级`guest/`。

`pre_review_qualification.json`、旧system/build/QuickJS receipts均保留原输入标识。
最终资格额外绑定runner/patch/builder SHA；builder要求全新output，每次复制输入再应用
本次补丁，实际重复output请求被拒绝的原诊断在上级inputs。所有大ELF/镜像/工作盘仍本地保留。
