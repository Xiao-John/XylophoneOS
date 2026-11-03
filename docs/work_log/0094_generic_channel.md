# 0094：有界受控 IPC 通道

2026-10-29。在 0093 本地认领后实现 sys81：调用者可在自身和有完成记录的直接
子进程之间建立单向、单槽有界通道；参与者通过枚举取得内核认证的对端和控制者，
现有 send/recv 对通道验证实际 sender/receiver PID。读/写等待使用绝对截止时间，
原子登记并由 send/recv/close/进程退出唤醒；每控制者最多 4 条，仍受既有 21 端点
池约束。创建、关闭、发现与权限边界见[channel 契约](../contracts/channel.md)。
参与者或控制者死亡立即关闭通道，成功 exec 关闭相关通道，失败 exec 保持；fork
不会以新 PID 获旧通道权利。业务协议、事务和重连属于用户态，不在内核解释。

`python3 scripts/build.py --output-dir build/w1_generic_channel_20261029` 成功，
提交前 build ID `816871c525a743a9`；`channel_probe.cpp` 使用该 SDK 交叉编译、
链接成功，ELF SHA256 `fdc3406fac626a8b5be8d0a2139fe342491e5962d338b689df9da45dc7ffef6f`。
探针设计覆盖父子双向通信、枚举身份、立即等待、子代退出后的句柄失效；未运行。
文档一致性检查 466 链接、68 syscall、73 历史来源通过，当前 ABI 速查检查通过；
许可材料 7 项检查通过，不等于逐成员审计。

没有客体验证或完整竞争、配额、无效指针、未消费消息、fork/exec、退出/故障、
资源回收测试；manifest 标记 `implemented_unqualified`。该机制不是终端服务或 W1
完成。下一步用受控通道及 stream lease 实现用户态服务、模式和客户端，构造上述
负向探针；全部相关改动提交后再验收，之后才进行 W2 和 PR。
