# ncurses 双消费者客体探针准备

专用构建选项选择测试 supervisor；它启动真实终端服务，分别运行宽字符屏幕和
重入消费者。独立测试盘提供候选 xterm terminfo。宿主探针核对系统、SDK、库、
消费者和 terminfo 的来源与摘要，并检查中文输出、颜色、方向键、中文输入、
未知终端、尺寸和屏幕重入。此探针只覆盖这些行为，不代表完整 W1/W2 验收。
普通构建不选择该 supervisor；没有新增 ABI。

执行 `python3 scripts/build.py --ncurses-supervisor-probe --output-dir
build/w2_ncurses_guest_probe_20261031` 成功，build ID `71a861a35fdffc84`；
安装 ISO SHA-256 `450cab6c27495ab7d21be0c295eae3fdffb33583a17ac68c67b3c1d482b15d5d`，
终端 ELF SHA-256 `61bc071bb6a175a8bc98ca432ceeb1bd9d030087d86bf1cd26c448dd50bde2d2`。
两个消费者以 `/tmp/xos_utf8_sdk_20261030b/sdk` 和有效 ncurses 归档重新交叉链接，
输出 `/tmp/xos_ncurses_consumers_v6_20261031`；两者均含 `.xos.tty` 标记。
Python 编译和 ABI 文档一致性检查通过。文档一致性检查未通过：工作区另有未跟踪的
`docs/tech_debt.md`，其中两个链接目标当前缺失；本组未修改该文件。

客体未运行。按用户要求，所有相关改动提交后再验收；其他工作区改动不属于本组，
不得覆盖。后续应在合适的干净快照重建并执行 `tests/ncurses_guest_probe.py`，保留
失败和串口证据并修复实际问题。前台集成、fork/exec、故障恢复及完整 W1/W2 仍未完成。
