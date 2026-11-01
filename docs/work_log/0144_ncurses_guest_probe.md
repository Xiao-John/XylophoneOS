# ncurses 双消费者客体探针准备

原记录中的机器临时目录已替换为 `${XOS_SCRATCH}` 路径模板；哈希和结果未改。

专用构建选项选择测试 supervisor；它启动真实终端服务，分别运行宽字符屏幕和
重入消费者。独立测试盘提供候选 xterm terminfo。宿主探针核对系统、SDK、库、
消费者和 terminfo 的来源与摘要，并检查中文输出、颜色、方向键、中文输入、
未知终端、尺寸和屏幕重入。此探针只覆盖这些行为，不代表完整 W1/W2 验收。
普通构建不选择该 supervisor；没有新增 ABI。

执行 `python3 scripts/build.py --ncurses-supervisor-probe --output-dir
build/w2_ncurses_guest_probe_20261031` 成功，build ID `71a861a35fdffc84`；
安装 ISO SHA-256 `450cab6c27495ab7d21be0c295eae3fdffb33583a17ac68c67b3c1d482b15d5d`，
终端 ELF SHA-256 `61bc071bb6a175a8bc98ca432ceeb1bd9d030087d86bf1cd26c448dd50bde2d2`。
两个消费者以 `${XOS_SCRATCH}/xos_utf8_sdk_20261030b/sdk` 和有效 ncurses 归档重新交叉链接，
输出 `${XOS_SCRATCH}/xos_ncurses_consumers_v6_20261031`；两者均含 `.xos.tty` 标记。
Python 编译和 ABI 文档一致性检查通过。文档一致性检查未通过：工作区另有未跟踪的
`docs/tech_debt.md`，其中两个链接目标当前缺失；本组未修改该文件。

提交 `09087cb` 后在隔离干净工作区重建同一 build 并运行
`tests/ncurses_guest_probe.py`：终端服务启动、xterm 初始化、红色中文输出及输入
就绪标记均已出现；发送左键和中文后消费者返回失败，原因尚未定位，重入探针未执行。
原始证据位于该工作区 `build/ncurses_guest_probe_serial.log` 和
`build/w2_ncurses_guest_probe/ncurses_guest_probe_report.json`，串口 SHA-256
`deb2639736c82512f7ee336f7790b4a182fe21c004c04da7b6c8663b3990f993`。
现增加子进程退出码诊断，须提交后重建重测并修复实际问题。
前台集成、fork/exec、故障恢复及完整 W1/W2 仍未完成。

提交 `14a17c6` 后重建 build `e51911dfbb5d30b5` 并重测，退出码为 6，
对应首次 `wget_wch` 未得到 `KEY_LEFT`；串口 SHA-256 为
`07cce1a3f4a2da1621ff1eaadb89d0f341f0576d3834cdbf7d3bf018dd76c256`。
目标 ncurses 配置的 `HAVE_SELECT` 为 0，亦未启用 poll；其 `_nc_timed_wait`
因此缺少这两种等待分支，这是需要优先排查的方向，尚未证明它是唯一原因。
诊断回执在隔离工作区 `build/w2_ncurses_guest_probe_diagnostic/`。
