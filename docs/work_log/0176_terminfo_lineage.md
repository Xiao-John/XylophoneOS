# xterm terminfo 来源链与交付说明

2026-11-02。上一轮确认固定的 `terminfo.src` 包含来源不明的历史内容；先检查本次
生成条目的实际源码依赖，保留上游自己的说明，再单独审视各继承内容与静态发行材料。
源码依赖图不能自动判断实际版权归属，也不能视为法律审查通过。

新增 `scripts/audit_terminfo_lineage.py`：核验压缩包、terminfo 构建回执、源文件和
编译条目的哈希，从 `xterm` 出发遍历 `use=`，遇到缺失或重名条目即拒绝。该工具只
提取源码依赖，不重现 tic 的覆盖、取消或解析语义。对 `build/w2_width_terminfo_6f2be7d/`
记录的 xterm，图含 49 个条目，最初链为 `xterm` → `xterm-new` → `xterm-p370`；
完整结果位于 `build/xterm_lineage_6f2be7d.json`，SHA-256
`82dc429db763d26fc34e2cc634bb818f1f6dcbfd61dd2170aff46c1bd4f19d3b`。连续两次运行结果一致。

SDK 组合过程现将锁定源码 `terminfo.src` 的上游来源说明一并放入 ncurses 许可材料，
并核对它与实际 terminfo 源文件开头逐字相同；材料哈希登记于 `licenses/components.json`。
这补充可复核的来源信息，并不决定数据许可证。提交后需要重新建立 SDK 和独立消费者、
运行组合客体与冻结验证；历史报告不对新交付包生效。49 个条目的逐项历史来源、其他
传递文件、newlib 成员以及实际发行法律要求仍待审查。
