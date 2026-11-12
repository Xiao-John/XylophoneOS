# SSG 传输期限修复与历史生命周期故障定位

2026-11-12。继 VM/COW/CPU 提交 `e43fbc51fbf8788ed275dffb1ab0b775e0f996d3`
之后，在同一隔离分支检查 SSG 的停止、关闭、取消、ACK，以及 D13/D14 和
0088 Pillow 历史故障。主代理并行处理 QPA 多窗口和客体 runner，本提交不修改
那些实现。本组修复一个独立的确定错误；三个历史故障仍为 **UNRESOLVED**。

## 已修：P4A 就绪返回后遗漏绝对期限检查

`pipe_event_sink::write_frame/read_exact` 和 Subscriber 的 `read_exact/write_ack`
原先只把期限交给 `sys_pipe_wait`。下一次非阻塞读写前没有重新看时间；内核
`sys_pipe_wait` 又是先判断就绪、再判断期限。因此，当调用线程恢复执行较晚，
或者就绪与期限同时发生时，已经过期的 ACK 仍可被当成完整 ACK 接受，已经
过期且尚未开始的事件仍可发送。这违反了现有
[P4A 契约](../contracts/ssg_p4a_subscriber.md)的有限传输期限和迟到 ACK 语义。

确定复现直接抽取真实传输函数：第一次读写返回 WOULD_BLOCK，随后 wait 返回
ready，同时可见单调时间从 10 变成 101，原期限为 100。旧实现继续读写并返回
complete。没有修改或重写待测传输逻辑，也没有用假的 Qt 对象验证 Qt 行为。

修复只在传输循环开始检查绝对期限，读取完成后再检查一次接受时的期限。
Subscriber 在 idle 状态先检查 session 期限，第一字节到达后仍按原设计开启
一个 frame 预算。发送前已经到期而尚未写出的事件保持 not_sent；事件已发送
后读 ACK 到期则由既有 publish 分支保持 UNKNOWN，不重放、不伪造未执行。
这不是硬实时保证，也不改变内核 pipe 就绪语义。

改动范围：

- `src/user/ssg/pipe_event_sink.hpp`：事件发送与 ACK 读取。
- `src/user/apps/ssg_subscriber.cpp`：事件接收与 ACK 发送。
- `src/user/ssg/pipe_wire.hpp`：纠正“sys_pipe_wait 无期限”的过期注释，P1
  watchdog 行为保持原样。
- P4A 契约、真实源码宿主回归和本记录。

## 实际验证

[本轮回执](../reports/ssg_deadline_lifecycle_20261112/result.json)、
[旧实现输出](../reports/ssg_deadline_lifecycle_20261112/baseline.txt)、
[修复后输出](../reports/ssg_deadline_lifecycle_20261112/current.txt)由平铺
[manifest](../reports/ssg_deadline_lifecycle_20261112/manifest.json)登记。
宿主为 `c++ (Debian 14.2.0-19) 14.2.0`、Python `3.12.14`。

```sh
python3 tests/ssg_deadline_host_test.py --revision 158a9b99550c03b97e74e3b9e4c2fd6a288c8bf3
python3 tests/ssg_deadline_host_test.py
```

第一条从本仓库固定历史读取实际源码，结果 **exit 1，20 项中 10 项失败**；
第二条结果 **exit 0，20/20 PASS**。测试编译真实的四个传输函数、真实 ACK
编码器以及 SDK 时钟入口；只有 syscall 传输和时刻由用例安排。覆盖：期限前
正常写入、就绪后重试、期限等值、迟到就绪、部分 ACK 期限、读完后期限、
Subscriber idle 与 frame 预算、ACK 发送，以及 EOF/truncation/内核 timeout。
`tests/docs_consistency.py` 通过（907 个本地链接、78 个 syscall、73 份历史源）；
`tests/report_manifest_check.py` 通过并包含本轮新目录；Python 语法和
`git diff --check` 通过。

没有安装真实宿主 Qt Core，也没有固定目标工具链或运行客体；本组 **Qt 应用
运行、目标链接、QEMU、D13/D14 重现和 Pillow 压力均 NOT_RUN**。宿主传输回归
不能替代这些项目。没有把下面的历史失败改成通过。

## D13：Studio 测试中的 legacy Qt 退出超时

核对
[首次 Studio 报告](../reports/aurora_midnight_dock_20261030/dock-desktop-studio/report.json)
及同目录 `serial.log.gz`，超时的是测试后段启动的 `/bin/legacy.elf`，不是已经
完成 UI 检查的独立 Studio 程序。串口末尾依次为 QPA input-thread-exit、
surface-destroyed input-thread-joined、`QT_WIDGETS_OK`；之后没有进程回收或 wait
完成。`tests/fixtures/qt6/widgets_probe.cpp` 在 `app.exec()` 返回后打印这个
标记，随后仍需析构局部 Qt 对象并经过 libc 进程退出。

据此只能把范围缩小到已退出事件循环之后的对象析构／运行库退出区间。
[相同测试的重试](../reports/aurora_midnight_dock_20261030/dock-studio-rerun/report.json)
通过不提供阻塞位置；首次材料没有线程 RIP/RSP、mutex owner 或析构阶段标记。
当前 QPA 已换为 Interactium，旧专有 surface 日志也不能作为新 QPA 的验收。

下一次须保留固定 ELF 与 SDK，超时发生时抓取各线程上下文、等待类型和目标、
进程 closing/exit_owner 状态，区分 QWidget/QApplication 析构、Qt TLS 清理、
newlib 锁和 process-wait。仅延长 harness 超时或重复运行不能给出根因。

## D14：SSG Consumer / Notes 退出超时

完整核对 P3C 的 `failure-watch-shutdown.tar.gz` 与
`failure-legacy-shutdown.tar.gz` 内原串口：Browser 和 Notes 都打印
`SSG_PROVIDER_END ... EOF`；Notes 收到 Escape 后 QPA input worker 退出并完成
join；Browser 正常回收，Notes 仍在 20 秒上限后被取消，退出码 -9。这说明至少
请求读取已经看到 EOF，不能继续把“请求 pipe 一直没 EOF”当成已证原因。

当前 `pipe_provider::stop` 先发布 stopping，关闭 0/2，再设置 mailbox 并 wake，
最后等待 worker。`pipe_release` 自历史提交 `8624c389` 起就在任意引用关闭时
无条件唤醒该 pipe 的双向等待者；这条路径当前仍存在。消费者的 native
watchdog 则在析构中发 stopped、wake、pthread_join。watch control 线程通过
原子取消标记退出传输，并在 source channel 关闭前 join。P4A 单个事件确认后
才发送下一个，ACK 错序或失败不被提升为已确认。上述源码核对未发现足以确认
原退出超时原因的遗漏。

原
[failure-history](../reports/ssg_p3c_engine_neutral_20261031/failure-history.json)
已经保留把 Provider 的 QThread 改成 native pthread 的候选：候选 8/8 与带
诊断原版 8/8 都没有复现。因此本轮没有再次采纳这个未经因果验证的候选，
也没有为“也许是竞态”新增等待层。线程契约明确：强制停止其他线程后，普通
exit 清理可能遇到它们持有的用户锁，应用应先 join；但原故障没有锁持有者
或 native TLS 阶段记录，不能据此判定就是这条边界。

需要在匹配当前 SDK 的真实运行中记录：provider run 返回、stop wait 开始／
结束、native TSS/reent 清理完成、app.exec 返回、Qt 对象析构结束，以及被卡住
线程的栈和锁持有者。失败原件和未复现对照应同时保留。本次 deadline 修复
解决的是迟到传输被接受，**不关闭 D14**。

## Pillow：原 `_malloc_r` 缺页仍未定位

读取
[原公开故障报告](../reports/modern2_python_20261029/failures/guest-attempt2/report.redacted.json)、
该目录 `dash_success.log.gz`、`serial.redacted.log.gz` 以及
[资格记录](../reports/modern2_python_20261029/qualification.json)：exec 主线程
TID 17、故障 worker TID 20，vector 14、RIP `0x4037927b`、CR2 `0x60cc5fc8`；
旧记录将指令定位在 newlib `_malloc_r` top-chunk header 写入。故障 CR2 在
既有 heap 地址区间，但原现场没有 RSP、page-fault error、页表状态、当前
heap_break 或 allocator top/锁状态，不能区分已损坏 chunk 指针和映射问题。

本轮核对 `thread_context.cpp` 的每线程 TLS/control 布局、pthread TLS/TSS/
reent 清理顺序、newlib retargetable malloc 锁桥、`_sbrk` 的 break mutex 与
内核 heap 映射增减/失败回滚，以及 exec 后初始 TLS 建立；没有从这些代码
得到可复现的错误路径。普通仓库 `libc.a` 不能代替故障所用线程 profile 做
allocator 因果证明。

保存的早期 `721430686d273598f27c` 和最终 `d2d064e8db8332bc7d91`
CPython 构建回执都记录同一线程 SDK manifest SHA256：
`a203fbda0b9d984d60e3271c33418d3b796f77060b3cba4661bc0be2eb4117b7`。
其中线程 newlib `libc.a` 的 SHA256 为
`d252bb6f1e37133f5e62e3c6a6b6fef337a75e2c22f7b101d63eea5a0fbd9e28`。
这进一步说明后续七个有限对照通过不是一次 runtime/allocator 修复的证据。
该线程 archive、原故障 ELF/工作盘在当前环境不可用，不能拿宿主 glibc/Pillow
运行冒充原目标验证。

下一次应从锁定源码重建同一线程 profile，保留符号，在原 dash fork/exec +
Pillow worker 输入上记录 fault RSP/错误码、TID/FS/control、heap_break、CR2
对应 PTE、malloc top 指针/大小和 malloc/break 锁 owner，并与 xsh、原 CPython
pthread 与 native zlib 对照。已有全回收观察只说明进程回收，不证明堆正确。
**Pillow threaded 和完整 LocalPilot 仍不能据本轮声明可用。**
