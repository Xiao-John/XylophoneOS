# 67ddbd3b：IPC 契约与 seL4 参考路线

2026-11-10。按标题生成工作记录编号。应用户要求先设计应用/服务与内核可并行推进的
高性能 IPC，暂不开展 VM3。基线 main `d708790`；VM2 #102 为独立 PR，不以其为主线事实。

新增 [IPC v1 提案](../contracts/ipc_v1.md)和 [实施计划](../plans/ipc_sel4.md)：
区分现有单槽异步 IPC 与候选同步 endpoint；定义认证 badge、一次性 reply、deadline、
取消/结果未知、wait、通知、授权、迁移和阶段验收；以 feature 协商让应用可依契约
设计，同时禁止把模型或缺失后端冒充 SDK supported。暂不登记 syscall、发布 ABI、修改
现有行为或引入共享内存；VM3、COW 与共享 grant 分开。

参考 seL4 官方 IPC 与 notification 教程，核对 rendezvous、badge、reply 和其
fastpath 前提；XOS 未实现、未证明 seL4 等价。当前计划的字节布局、数值、限额仍由
后续独立 ABI 登记冻结。未构建镜像、未执行客体或性能测试；本组仅文档。
下一步评审待冻结点，并先登记再实施真实 ABI；基线测量和参考状态机可独立推进。
