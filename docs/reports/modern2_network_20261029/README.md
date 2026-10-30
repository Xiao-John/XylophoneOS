# N2维护者审查与实施接续包

2026-10-29。**N2 = BLOCKED**。本分支基于本轮重新fetch的 upstream main
`aaec2e9d8ffe61ce1d523cd56852d36cde3edd07`，仅交付审查输入与验收设计。
没有实现或调用提案中的syscall112，没有自行批准、合并或添加SDK supported声明。
网络交付不构成本轮要求的“真实公共兼容能力”成功；该门槛须由独立的真实实现满足。

## 已重新核实的状态

[公开PR快照](pr_snapshot.json)采集于2026-10-29 19:54:38（北京时间）；
[固定输入校验](input_verification.json)保存18份提交内文件的SHA256、Git blob和字节数，
全部与当时checkout字节相同。快照是时点证据；实施前须再次fetch并重新核查。
空review、行内thread和conversation comment列表只表示公开接口未显示审查记录，
不能证明不存在私下讨论；但PR #18明确尚未合入，实施门槛仍未满足。

| 输入 | 本轮观察 | 能力边界 |
|---|---|---|
| [PR #17](https://github.com/Xiao-John/XylophoneOS/pull/17) | 已合入main；merge `aaec2e9` | FB1/FB2沿用其冻结输入，本轮未重验 |
| [PR #18](https://github.com/Xiao-John/XylophoneOS/pull/18) | Draft/open/unmerged；HEAD `97947c0`；公开review/threads/comments为空 | 112仅未合入提案的claimed，没有合法可调用入口 |
| [PR #20](https://github.com/Xiao-John/XylophoneOS/pull/20) | Draft/open/unmerged；HEAD `9b832fa`；公开review/threads/comments为空 | 原N1受限Ethernet诊断，不是运行期网络服务 |
| [PR #19](https://github.com/Xiao-John/XylophoneOS/pull/19) | Draft/open/unmerged；HEAD `88cdbc0`；公开review/threads/comments为空 | 本地HTML/CSS与独立HTTP解析器，未连接transport |
| [PR #21](https://github.com/Xiao-John/XylophoneOS/pull/21) | Draft/open/unmerged；HEAD `c152f7f93fb11291eb019d572219c2b4d69743a9` | QuickJS语言运行、Python依赖失败和HOST HTTP夹具，不是客体HTTP |

GitHub的mergeable字段可能因后台重算而改变，不把它当批准、无冲突证明或能力资格。
原N1系统build `67883ca24e9dcdae`、镜像SHA256
`f019c215cd7cec00d3a5f5bbdbe91f511d0c76325c9633c7baa5eecfda721d61`；
原Browser build `3fb1bb7d6b9e7bf9`、ELF SHA256
`86044be0fe0f4016fb1d98ffa5e1321e0928706e312e85fad2111dc4f33286dd`。
这些只为区分原资格，**没有重绑到aaec2e9或本轮新组合**。

## 维护者首先需要决定的事项

逐项依据、建议修订和关闭条件见[具体审查清单](review_decisions.md)。这里的审查结论是
源码/契约分析，不是维护者APPROVE，也不是对未运行实现的测试结论。

1. 保留单一有界复制入口、受认证主体与最小rights；不复用spawn-only的syscall28，
   不向用户放开BAR、PCI IO、物理页、DMA地址或原始设备控制。
2. 明确区分“仅对未启动child授予”与“撤销已运行owner”。现提案同时写了未启动限制与
   rights=0唤醒现有等待者，入口规则需要消除歧义，才能验真实撤销。
3. 冻结INFO、GRANT布局，right/event/错误数值、copyout失败的原子性，以及token代际耗尽规则。
   本交接包不抢先规定公共常量；它们由登记/实现负责人整合共享头与两个SDK。
4. 将N1的pre-run IRQ/DMA生命周期扩为普通用户态运行期间的设备机制，单独证明调度等待、
   owner故障、reset/quarantine；不能把旧boot-monitor的 `sti; hlt; cli` 直接搬进syscall等待。
5. PR #18完成维护者审查并合入claimed登记后，才开始公开机制实现；通过D1–D3再接lwIP。
   PR #20/#19各自的审查、冲突处理与组合资格仍需维护者正常流程。

## 最小验收与后续责任

[验收契约](acceptance_gates.md)给出可直接开工的D1–D3、N2A–N2D、失败及回归矩阵，
并规定客体请求、宿主新challenge、以太网抓包、TCP流、字节摘要和实际截图的绑定。
它是未来验收设计，不含虚构的结果、ELF、截图或客体执行命令。

| 责任角色 | 独占公共文件/范围 | 解锁条件 |
|---|---|---|
| 维护者/ABI登记负责人 | PR #18、ABI表与契约决议；分配公共实现负责人 | 审查并合入claimed；不以本docs PR替代 |
| 设备机制负责人 | process权限/代际、共享头、dispatch、普通/线程SDK和manifest、平台NIC适配、退出回收 | 已合入登记；D1–D3通过且原失败保留 |
| 用户态网络服务负责人 | lwIP glue、网络服务身份/IPC协议、连接配额/超时/close/退出 | 使用已验桥接，先N2A再N2C；无新ABI抢号 |
| Aurora负责人 | 既有browser_http/本地引擎的有界网络provider、来源与资源策略 | N2C真实响应后再N2D；浏览器不获设备rights |
| TLS负责人 | CA、链/主机名/时间、随机数、失败策略 | 独立安全验收；禁止insecure和静默HTTP降级 |

lwIP继续锁定2.2.1 / `77dcd25a72509eb83f72b033d219b1d40cd8eb95`；原archive
SHA256 `ddce54f8e7d61f6462e56a22fe9f70c4f1162e4d1306d7809c5aeed9ee5ca68c`。
它启用NO_SYS和有界raw API，socket/netconn关闭，单用户态event loop拥有全部lwIP状态；
`sys_now`与`xos_lwip_random`仍须真实绑定XOS单调时钟/随机数。其archive成功不证明协议运行。

## 本轮验证与明确未运行

本轮执行固定提交文件字节校验、文档一致性、ABI文档一致性和差异空白检查，原始输出见
`checks/`。没有公共运行时代码变更，不为本docs分支新建系统/SDK/镜像或重跑旧QEMU。
因此本轮所有D/N2客体gate、内存测量、资源计数、HTTPS均 **NOT_RUN / BLOCKED**。
无可报告的新客体峰值/基线，不挪用原N1的34 DMA页或原浏览器7558页样本作为新组合数据。

状态区分：真实系统能力仍为原N1的Ethernet/IRQ/DMA；解释器能力是原QuickJS语言执行；
Web平台仅原B1受限本地HTML/CSS；Chromium、LocalPilot、Code - OSS应用兼容仍BLOCKED；
新产品或正式发行资格NOT_RUN。
