# 0089：显式截止时间与串口输入等待

2026-10-29。复用已有 sys54 描述符校验与阻塞机制，第三参数非零时解释为绝对单调
截止时间；单核内核在同一不可抢占区间检查输入、登记等待，串口 IRQ 使可读等待者
就绪，时间到期返回 `thread_error_timeout`。管道可使用相同截止时间；新 console 等待
只允许有可读 route 的调用者，close 唤醒本进程等待者并返回 denied。允许伪唤醒，
需要重新读取；就绪优先于已过期截止时间。原第三参数为零时，console 仍返回
would-block，原 libc 的非阻塞行为保持。无新增 syscall 编号，详细语义见
`e04_loader_sdk.md`。

这不是前台独占或认证终端服务：旧 console route 仍可共享，Escape 取消仍可能抢占
输入；没有多源等待、设备关闭/EOF、模式恢复或 POSIX poll。两个 SDK 生成器仅以
`implemented_unqualified` 记录扩展，不能宣称目标资格通过。

`python3 scripts/build.py --output-dir build/w1_explicit_wait_final_20261029` 通过，
提交前 build ID `5f19915ebc98719b`。独立 `wait_probe.cpp` 使用该 SDK 头/静态库
交叉编译和链接成功，设计覆盖管道定时、就绪优先、关闭及 console IRQ 唤醒；尚未在
客体运行，也未覆盖竞争、同时关闭、异常、溢出和长时间资源回收。
`tests/abi_doc_consistency.py` 通过；`tests/docs_consistency.py` 首次因 registry 表格
格式不符失败，恢复既有表格格式后通过（458 链接、66 syscall、73 历史来源）。
所有相关修改提交后才进行客体验收；该提交前镜像不作为客体验收证据。
