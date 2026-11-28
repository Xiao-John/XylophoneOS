# P1 C D catalog and publisher protocol coordination

2026-11-28，Asia/Shanghai。

## 目的与范围

为并行P1-C/D实现登记明确的catalog查询、动态capsule版本、受限发行查询和
publisher启动消息。这里只提交协调登记，实际实现及验收仍由独立C/D PR交付。
现有P1-H/K和Net2 operation21登记保持各自范围。

## 已固定的接口

详见[ABI登记](../contracts/abi_registry.md)：PCQ1/version1 request40/reply784；
64字节authority与728字节catalog；显式capsule v3；PPR1新增op12/13并保持
1592/1560字节及1–11编号；XYPMSUP1精确96字节四阶段bootstrap。
各入口明确实际kernel peer、角色、有限期限、失败/未知处理和旧产物边界。

## 验收状态

本PR没有修改运行时代码，没有运行客体，不声称完成C或D。真实GNU
posix_spawn后代与same-PID exec属于C的授权验收；shared GNU fork当前ENOSYS，
其能力和controller迁移继续属于独立P1-K2，不能被本登记提升为supported。

本登记只运行文档/ABI一致性、公开证据路径和diff检查；各实现PR必须绑定
其最终SDK、原始输入、真实客体结果与失败记录。

实际检查通过：完整checkout的文档检查2339个本地链接、79个已分配syscall、73个历史源；
ABI一致性PASS；actual-index公开路径2/2无发现；git diff --cached --check通过。
