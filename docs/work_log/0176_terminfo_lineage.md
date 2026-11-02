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

提交 `335b2f03988769c541f759ba12bf5ee69893c8a0` 后重建系统及组合 SDK：系统 build
ID `7ad95c4f8b516671`，组合 SDK 树 SHA-256
`e4a480d0e4083be3e4f839133275a6eb92f27daa72194819030aaca18937497c`。正常 Xsh 客体
`passed_probe`，串口 SHA-256
`d150c03b34989ba9cd5a91bb174259a078699ac43a7fe4bfe70e7aeffd4838b2`；冻结结果
`guest_verified_subset` 位于 `build/w2_lineage_frozen_335b2f0/`，树 SHA-256
`6f32ecbe209501b825250396988a99ac328d7c8f411d5ab308210dc8c0d32cb7`。重建后的
tty_exec 和 channel 客体各为 `passed_subset`；目标库的 162 成员来源筛查及材料哈希
检查通过。将测试用副本的 terminfo 源说明改坏后，组合步骤在创建输出前拒绝。所有
结果均只覆盖相应报告列出的子集，不能提升为完整 W1/W2 或许可审查通过。
