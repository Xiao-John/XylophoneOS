# afc82730 · ClarkE 双 Shell 网络绑定

2026-11-26 · 以受信静态安装 profile `61991375` 与解析 referral 修正 `3ff22f72`
的组合树为基线。Xsh 为受信安装配置下的子进程建立 `XOS_NET_SERVICE_PID` 启动快照。
Dash 通过原有环境导出路径传递。用户以 `clarke.elf --network` 选用快照。ClarkE 在
任何 DNS 或 TCP 操作前核对 IPC 两方向的实际内核对端。服务正常停止并替换后，重新
从 xsh 或新启动的 dash 取得绑定。开发用途仍可传显式 PID。
[绑定、生命周期和 ABI 边界](../contracts/network_n4_v1_proposal.md#22-静态安装-profile)

## 安装与重启实测

`6face2ba` 以同套 glibc SDK/profile 重新编译 ClarkE、重建并安装 XPK。镜像
`2f1bd2e61b542333` 使用固定 `10.0.2.3` resolver、`10.0.2.2` TLS 对端和测试 CA。
QEMU 11.1.3 回放同一安装工作盘。xsh 和 dash 各在一轮冷启动中验证初次启动、停止
服务、以同一受信安装配置启动替换服务，以及新旧绑定行为。

| 入口 | 启动 PID | 替换 PID | 旧绑定输入 | 结果 |
| --- | ---: | ---: | --- | --- |
| xsh | 9 | 14 | 既有显式 PID | HTTPS 拒绝，DNS 和 TLS 对端无流量 |
| dash | 9 | 15 | 保留旧值的启动环境 | HTTPS 拒绝，DNS 和 TLS 对端无流量 |

四次合法 `--network` 启动均展示响应的 HTML、同源 CSS 和 BMP。两段 PCAP 分别
捕获两个到固定 resolver 的 A 查询。对端共记录十二次正确 SNI、HTTP Host 与双向
TLS 关闭。每次启动和拒绝后均恢复 121374 个空闲页、6 个任务和 4 个完成记录，
两轮替换后的网络服务均正常退出。普通镜像 `b9a462501e4af36a` 在两种 Shell 启动
`--network` 时均以状态 2 退出，Dash 直接查得变量缺失。

同一冷启动内 PID 由内核高水位分配，耗尽即拒绝。两个冷启动都可见数值 9，IPC
会话与启动快照皆在各自客体重新建立。另用普通镜像及其 SDK 运行三轮 IPC exec 客体，
失败的 exec 保留既有端点，成功的 exec 撤销双向端点、名称和排队连接。同 PID 重新
连接使用新端点。绑定验证的边界是当前进程身份和端点寿命。
[组合验收回执](../reports/n4_shell_network_binding_20261126/manifest.json)

## 复验入口

沿用 [静态安装配置](e9955e4f_network_static_profile.md)，并提供从同一源码树新构建的
普通镜像，以 `--ordinary-system` 传给 `tests/clarke_static_profile_guest.py`。同源
普通镜像 SDK 通过 `scripts/build_ipc_exec_probe.py` 构建探针，使用 `tests/ipc_exec_guest.py`
的 `--repeat 3 --serial-only` 单独运行。两镜像各已通过 10 项许可材料，开放项为零。
