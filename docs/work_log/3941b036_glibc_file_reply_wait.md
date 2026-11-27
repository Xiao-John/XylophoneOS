# 3941b036 · glibc 文件回复就绪等待

静态装载器仍逐页读取用户态 ELF，文件请求仍通过认证的旧式 files 会话。
这次在现有 sys85 `file_reply_until` 模式下复用原子就绪检查、唤醒和单调期限。
Files 终止会唤醒已阻塞的对端，既有清理路径随后撤销端点。glibc 保留同一个
绝对截止时间和响应序号校验。旧内核只在返回原参数无效错误时沿既有定时轮询。
[实施计划](../plans/glibc_file_reply_wait.md)
[IPC 契约](../contracts/ipc_endpoint_lifecycle.md#文件回复等待)

## 工件和真实客体

在独立 Linux arm64 环境用锁定的 glibc 2.44 原档及已验签材料重新构建静态 C SDK。
接着实际构建 Dash 0.5.13.5，并用新库链接文件等待夹具。普通和 Files 故障镜像由
同一源码检出分别构建。客体测试使用独立 FAT 工作盘，逐一读回并验证加载的工件。

普通镜像 `03e4bb24004fd549` 中，xsh 和新 Dash 都验证回复已排队和阻塞后
唤醒、过期与错误端点，并以两线程对相同描述符完成 128 次定位读。ESC 取消后
资源恢复。故障镜像 `78e00b80081324c9` 中，实际服务终止唤醒已经等待的
接收者，旧 token 失效。另一启动从新 glibc 的公开文件入口验证首次和后续 EIO。
普通镜像还跑了两轮原 sys84–86 IPC exec 生命周期。
[客体回执](../reports/glibc_file_reply_wait_20261127/guest.json)
[IPC 回归](../reports/glibc_file_reply_wait_20261127/ipc-exec.json)

新 C SDK 链接的同样夹具和 Dash 放回旧内核 `81c419d562a3731e`。xsh 和 Dash
的并发读合计 256 次，资源恢复。该结果直接验证旧内核回退。
[旧内核回执](../reports/glibc_file_reply_wait_20261127/legacy.json)

主机 ASan/UBSan 通过 58 个 glibc 文件会话及描述符用例和 15 组真实 Files/FatFs
集成。该主机测试替换系统调用边界，覆盖旧内核、虚假就绪后复等、截止竞争、模拟中断、
死亡和重复应答。实际 POSIX 信号递送未在本次扩展。实际进程取消由客体覆盖。
[主机回执](../reports/glibc_file_reply_wait_20261127/host.json)

## 固定请求吞吐

同一普通镜像和 FAT 文件运行三段定位读取。每段 96 次请求、192 KiB，数据校验和
相同。两段正式就绪等待为 80 与 90 ms（2.344 与 2.083 MiB/s），均未调用睡眠。
中间对照只在诊断程序内模拟旧内核返回参数无效，实际走原 1 ms 定时回退，
耗时 970 ms（0.193 MiB/s）。97 次空接收对应 97 次睡眠。报告保存每条请求的
统一系统单调时钟区间、读长度和等待数。
[吞吐](../reports/glibc_file_reply_wait_20261127/transport-timing.json)
[原始串口](../reports/glibc_file_reply_wait_20261127/transport.serial.log.gz)

## Qt Quick 首帧

固定原来已搬移并链接的 Qt Quick ELF `276ef5bd5fb163b0c500ffdcd527e681d85c82829a19bdb282a80aa65a5d41c9`，
用实际由新静态 C SDK 重链的 Dash `60d0a0a3f750205d1972c673674aec61203534a628c0b13d320417f7c6f92037`
启动。两种宿主均用默认 60 秒门槛。macOS QEMU TCG 的 xsh 首帧为 10.146 秒，
Dash 为 7.812 秒。此前同宿主旧 SDK 的 Dash 为 137.281 秒，原始回执保持原绑定。
Linux QEMU 的两项分别为 14.315 和 11.939 秒。

两种入口均完成两轮字体、动画、A 键变色、B 键关闭并重新打开，输入线程和服务
退出后资源恢复。此对照覆盖新 Dash 和已发布评审的 Qt Quick 应用互操作，Qt 应用
保留先前 C/C++ SDK 的实际链接产物。
[macOS 回执](../reports/glibc_file_reply_wait_20261127/quick.json)
[Linux 回执](../reports/glibc_file_reply_wait_20261127/quick-linux.json)
[SDK 和系统绑定](../reports/glibc_file_reply_wait_20261127/binding.json)

对主线 `502cc673`、Qt Quick `ff4a6e5e` 和等候实现 `ad9de34d` 进行本地
组合，得到 `af8345e7`、tree `7dd03cb7`。从该树重建普通及 Files 故障镜像。
组合普通 ISO `698345e42bcadac3` 的两个图形入口再次通过默认 60 秒门槛，
xsh 首帧 10.887 秒，Dash 首帧 12.953 秒。组合文件就绪、并发、取消和死亡
也重新跑过。
[组合首帧](../reports/glibc_file_reply_wait_20261127/combined_quick.json)
[组合文件等待](../reports/glibc_file_reply_wait_20261127/combined_readiness.json)
[组合 Git 和镜像绑定](../reports/glibc_file_reply_wait_20261127/combined_binding.json)
