# cdd9b996 · 静态安装网络与 Pumpkin 登录构建的组合复验

2026-11-26 · 在含 #285 的主线解开 #286 的构建入口冲突，并在 #287 合入后的主线
`9ed4428d` 重建和复验。`build_users`
同时接收 `pumpkin_mobius` 和 `net_static_profile` 两个关键字配置。构建器仍在创建输出前
拒绝将普通 Xsh 的静态网络配置与独占 COM1 的 anchored Pumpkin 入口同镜像启用。
实际复验分别在普通镜像、静态网络镜像和两种专用登录镜像进行。

## 构建与输入核对

使用锁定 lwIP 归档、主机交叉工具和 `scripts/build.py --output-dir` 重建普通镜像
`568a0a5796b487ba`、静态网络镜像 `a3ca99f06c828a59`、旧登录镜像 `6fe3b78b6e9920a8`
及绑定真实 Mobius ELF 的登录镜像 `07c5e448431211be`。四份清单分别核对 1899 个基线
源码字节和所有产物。通过静态镜像提供的 SDK 重建 dash，由 `scripts/build_install_iso.py`
生成真实安装介质。四套镜像各通过 10 项许可材料检查，开放项为零。

#285 扩充 `execution.hpp`，导致已有 ClarkE 回执在读取旧头摘要时预检退出。以 #285
合成树快照、已锁定 glibc C++ SDK、配套 Qt Widgets、Mbed TLS 和同一试验 CA，通过
`src/ports/aurora_browser/glibc/build.py --tls-resolve-net2` 和 `scripts/package_desktop_products.py`
重新构建和打包。新回执绑定重新编译的 ELF、SDK、实际头文件和组装的 XPK。首轮并行
编译的编译器进程被宿主终止，正式回执取自独立输出目录中通过的单任务构建。#287
改变系统打包输入，因而重建四套系统并重新核对 ClarkE 回执内的全部仓库输入。

## 客体验收

按[安装回放入口](38cd52b2_network_shell_post283.md)，使用冻结镜像和源码，以
`tests/clarke_static_profile_guest.py` 在 Linux arm64 私有容器的 QEMU 11.1.3 里启动。
使用 `tests/ipc_exec_guest.py --repeat 3 --serial-only` 跑普通镜像。两个独立登录镜像分别
运行 `tests/pumpkin_user_login_guest.py` 和 `tests/pumpkin_mobius_guest.py`，使用主机
QEMU 11.1.2。

静态安装镜像从同一个工作盘两次冷启动。xsh 的网络服务 PID 从 9 换到 14，dash 的
从 9 换到 15。两个旧绑定在 DNS 或 TCP 发包前被拒绝，四次有效页面均验 HTML、同源
CSS、BMP 及渲染图像。两份抓包各记录两笔到 `10.0.2.3:53` 的 DNS 查询，对端完成 12 次
TLS 双向关闭。每次应用退出后均恢复 121373 个空闲页、6 个任务和 4 个完成记录。普通
镜像的两种 Shell 确认启动网络浏览所需的绑定缺失，同源镜像的 3 轮 IPC exec 确认撤销
旧端点和同 PID 建立新端点仍有效。

原有登录 13 项通过。首次 Mobius 回放在 QMP 握手时超时，保留原始失败回执并用同一
镜像独占重跑。重跑完成 5 项检查，两帧读回、注销和之后的持久吊销均得到验证。

Net2 客户端、ABI 表和工作盘 FAT 缓存通过宿主回归。ASan/UBSan 下以真实 lwIP 通过
25 项服务检查和 2 项主循环检查。#287 新增栅格目标，不修改这些检查的源码输入。

客体边界为静态 IPv4、受控 DNS、私有 CA 和已编译的 liteHTML 路径。专用 Pumpkin
开发镜像继续拥有其绑定桌面和凭据生命周期。跨登录席位交付可信网络配置、DHCP、产品
CA 包和完整 WebCore 仍需各自验证。

[系统、SDK、安装工件、截图、抓包及测试回执](../reports/n4_shell_network_post287_20261126/manifest.json)
