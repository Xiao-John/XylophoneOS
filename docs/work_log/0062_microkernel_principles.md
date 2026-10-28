# 0062：微内核与弱ISA依赖原则补充

2026-10-27。用户确认主端与GPT-6.1 Terra独立评审后的建议，要求写入宪法、仅本地提交，
随下次PR上交。本地分支codex/microkernel_principles，文档基线0fe87d8（PR #5头）。

## 决定与范围

宪法v1.1新增C20–C26：入核必要性、通用机制/服务协议边界、可信授权与不扩权委派、
通用语义/ISA表示分离、可检查的依赖方向、服务故障/用户态恢复边界，以及可退出的临时例外。
完整规范只在xos_plan.md维护，不在此重复一份条文；原则已获本次用户确认。

不可抢占路径的工作量上界、真实阻塞/交还调度、锁序与启动/panic边界写入线程专项契约，
不将固定时延、批次或算法升为宪法。没有因此要求所有驱动用户态、完整capability框架、
跨ISA二进制兼容、先实现第二ISA或自动服务恢复，也不新增逐接口用户审批。

本组只改docs/xos_plan.md、docs/contracts/threading.md、docs/state.md和本记录。
独立评审的显示IPC耦合/设备层ISA操作仅为后续审查线索；未修实现、未做全内核审计，
不默认现有实现符合新条款，不追改旧验收结果或源码/SDK/镜像绑定。

## 检查与交接

执行文档链接/锚点、ABI登记、历史来源检查及现有SDK当前表检查，均通过：

```text
python3 tests/docs_consistency.py --output-dir build/microkernel_principles
python3 tests/abi_doc_consistency.py --output-dir build/microkernel_principles
git diff --check
```

未改运行时代码、ABI编号、冻结报告或发行资产；未重建系统/SDK，未重跑客体/压力测试。
按用户要求只在本地提交，不推送、不更新PR #5或新建PR；下次交付须携带本分支提交，
若PR #5已squash，先核新基线再转接提交，避免把文档重组重复列入下次PR。
本组文档占用解除，无源码/构建占用。
