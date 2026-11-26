# e9955e4f · N4 受信静态安装配置

2026-11-26 · 在已验收的 net2 票据和 ClarkE 路径上增加可选静态安装配置。安装维护者
在构建时选定 PCI instance 和静态子网内的 resolver。系统指纹绑定输入 JSON，可信
启动映像内的 Xsh 在持久恢复门开放后按 profile 授予 NIC 并启动原生网络服务。服务在
epoch 1 公布经过校验的快照。ClarkE 从命令参数接收 Xsh 给出的实际 PID，并按既有
认证会话逐一核实端点。常规镜像、开发诊断与此配置有独立构建入口。
[协议和兼容约束](../contracts/network_n4_v1_proposal.md#22-静态安装-profile)

## 验收

系统 `02730f7823e080de` 的正式安装 ISO 含现有 dash 产物。验收先在工作盘安装
ClarkE XPK，再由 ISO 首次启动安装 dash。xsh 使用 PATH 启动 ClarkE。第二次冷启动
复用工作盘，由已安装的 dash 启动同一浏览器，dash 读到浏览器退出码 0。两个客体都
执行受信启动，拒绝 `net-start 42` 覆盖选定的 instance 41。

两段以太网抓包各记录一次对 `10.0.2.3:53` 的真实解析，TLS 对端在 `10.0.2.2`。
两个页面均核对新鲜 HTML、CSS 和 BMP 的摘要及 800×600 图像。对端核对六个预期
SNI、六个 HTTP Host 和六次 TLS 双向关闭。两次启动的应用退出都恢复 121374 个空闲页、
6 个任务及 4 个完成记录。停网分别返回 `close=0`。

普通镜像 `a3a81c739cf0ec1a` 通过旧版服务对照，配置探测返回 unsupported，原
op1 可用，抓包零 DNS。两镜像各通过 10 项许可材料。宿主 N2 在 ASan/UBSan 下通过
25 项传输与 2 项主循环检查，并复验 SDK 和构建配置输入拒绝。
[安装与普通镜像回执、串口、抓包、截图](../reports/n4_static_profile_20261126/manifest.json)

## 复验入口

使用有 `revision`、`pci_instance` 和 `resolver` 的安装维护者文件。报告目录包含
本次使用的 JSON。系统构建使用经锁定的 lwIP 归档。

```sh
XOS_LWIP_SOURCE_ARCHIVE="$LWIP" python3 scripts/build.py --net-static-profile "$STATIC_PROFILE" \
  --output-dir "$SYSTEM"
python3 scripts/build_install_iso.py --build-dir "$SYSTEM" --dash-manifest "$DASH_MANIFEST"
```

按 [ClarkE 构建合同](../contracts/aurora_browser.md#controlled-https-guest-build)
用同一 SDK/profile 构建和打包，选择 `--tls-resolve-net2`。运行 `tests/clarke_static_profile_guest.py`
时传入系统、源码、安装 ISO、安装清单、ELF、XPK、SDK profile、测试证书和静态 profile，
并在 `--network none --dns 127.0.0.1` 的独立 Linux 容器中用 QEMU 11.1.3 验证。

本次验收范围为单机受信启动、静态子网和私有 CA。现场可改配置、跨独立登录会话的
可信实例交付、DHCP 和产品证书信任库由各专项验收。
