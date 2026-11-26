# ec7eff4e · ClarkE 接入认证 net2 解析

2026-11-26 · 依赖 `bbf85269` 的 N4 静态解析扩展。ClarkE 的私有 HTTPS 构建
增加 `--tls-resolve-net2`。每条 TLS 连接在同一个认证 net2 会话完成配置探测、
解析票据消费和 TCP open。客户端检查结果的配置代际和有效期，TLS 传输只接受
预置地址，保持 URL 域名作为 TLS SNI、证书校验名及 HTTP Host。现有数字 IPv4
HTTP 与显式 pinned HTTPS 分别走现有传输路径。DNS 调用使用可复用的 C++ net2 客户端。
[浏览器构建及验收入口](../contracts/aurora_browser.md#controlled-https-guest-build)

## 绑定验收

安装真实 glibc Qt Widgets ClarkE XPK。系统用 `--net-dns-probe` 构建，启动后由
受信 xsh 显式开启 resolver。ARM64 Linux 容器使用 `--network none --dns 127.0.0.1`，
在同一隔离环境内运行 QEMU、私有 DNS A 记录服务和私有 CA 的 TLS 1.3 对端。
原有 3 秒导航总时限、同源限制、地址约束与 TLS 双向关闭均按产品路径执行。

镜像 `0a702f30cad8abeb` 与 QEMU 11.1.3 通过六项客体验收。浏览器收到 HTML、同源
CSS 和 BMP，客体 800×600 scanout 中样式背景、前景和 BMP 分别观察到 226684、1462
和 1024 个像素。对端核对六次 TLS SNI、四次 HTTP Host 和双向 TLS 关闭。浏览器拒绝
明文样式表、未知 CA 和同一可信链内不匹配的 SAN。xsh 切换到 epoch 4 后 DNS 返回
`10.0.2.99`，浏览器在 TCP open 前拒绝该地址。五次进程退出都恢复 121426 个空闲页、
6 个任务及 4 个完成记录。N2 停止返回 `close=0`。

早期试验中第三个资源未加载。补齐串口诊断后确认它返回 `-26624`（TLS 期限）。
复验对端按 native 客户端的无会话恢复配置关闭 TLS 会话票据。30 秒 DNS TTL 可能
跨独立浏览器启动而到期，runner 按同一次导航检查三份资源共用一次 DNS 查询，
再独立核对配置换代后新查询的返回值和 TCP 连接数。

现有 pinned native TLS 真实客体另完成八个场景，覆盖合法链、身份/信任链错误、
过期、关闭截断与无熵环境。宿主 HTTP parser 运行 211 项检查与 4096 个输入向量，
带 AddressSanitizer 和 UndefinedBehaviorSanitizer。预览系统许可材料 10 项通过，
开放项为零。[绑定回执与原始证据](../reports/clarke_net2_dns_20261126/manifest.json)

本次依旧使用私有静态地址、私有 CA 和 liteHTML。公网 resolver、DHCP、系统默认
信任库以及更广泛的浏览器运行环境仍有各自验收门。
