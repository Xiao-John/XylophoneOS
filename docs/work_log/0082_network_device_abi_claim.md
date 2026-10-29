# 0082 网络设备机制认领（仅设计登记）

2026-10-29，基于重新fetch的upstream `39083f9968d84b5679c86a74a6c8394033c0d915`。
PR #13/#16已合并，#17仍open；所有旧worktree、分支、build和冻结报告保留。
实际差异：ABI登记只提出112 reserved/claimed，无代码常量、系统调用实现或SDK能力。

当前PCI映射只能内核调用，普通应用没有网卡endpoint/right；现有28是spawn_depth授予，
不能承载设备访问；PIC/IDT缺PCI IRQ路线。设计见[提案](../contracts/network_device_v1_proposal.md)。
已在N1候选`67883ca24e9dcdae`的实际BAR映射与32帧收发后，重跑普通应用MMIO/PCI IO
失败探针：vector14/13与精确资源回收。冻结[回执](../reports/network_device_gap_20261029/README.md)
绑定新镜像、SDK、ELF和测试输入；不能冒称新公开机制或TCP成功。

本分支与`codex/browser-net-n1`驱动、`codex/aurora-browser-b1`浏览器分离；各自私有build。
负责人Codex负责本登记和公共文件整合；驱动负责内核/IRQ，浏览器不改公共ABI/Qt底座。
不触碰FB1/FB2工作区或未合并功能，不改main、代理/TUN、其他项目或Release。

实际执行`python3 tests/docs_consistency.py`、`python3 tests/abi_doc_consistency.py
--output-dir build/network_abi/audit`及`git diff --check`通过（457本地链接、66已分配syscall、
73历史来源）。本登记不提供N1整体资格；N2/B1/B2、HTTPS、
JS、静态产品发行许可在本登记PR均NOT_RUN。合入前公开设备接口实施BLOCKED，
并不阻止独立N1驱动和本地HTML/CSS浏览器工程继续。下一步：审查并合入claimed登记，
按提案冻结结构/错误数值，统一实施共享头、dispatch、SDK/manifest、权利/回收测试。
