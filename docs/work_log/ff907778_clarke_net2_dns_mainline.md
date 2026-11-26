# ff907778 · ClarkE 认证解析合入票据基线复验

2026-11-26 · 以已验收票据树 `ebdbdd27` 为父，迁入六个 ClarkE 提交。六组补丁无
冲突，原始报告的 13 个文件逐字节保留，根清单采用仓库规定的 SHA-256 字符串值。
[初次验收](../reports/clarke_net2_dns_20261126/manifest.json)

从 `ff907778` 重建启用 `--net-dns-probe` 的系统 `e881f2dae4a34daf`。用锁定的
glibc SDK/profile 与 Qt Widgets 归档重新编译 ClarkE 和 Mbed TLS，生成新 XPK。
运行 `tests/clarke_https_guest.py`，由被隔离的 ARM64 Linux 容器运行 QEMU 11.1.3、
回环 DNS 和 TLS 1.3 对端。重建的镜像、ELF、XPK、SDK profile、TLS 回执和客体结果
绑定在新清单中。[复验证据](../reports/clarke_net2_dns_mainline_20261126/manifest.json)

六项客体验收通过。浏览器验证 HTML、同源 CSS、BMP 的响应字节并显示在 800×600
scanout，样式背景、前景和 BMP 像素分别为 226726、1460、1024。对端收到六次相同域名
的 SNI、四个带预期 Host 的 HTTP 请求与四次双向关闭。浏览器分别拒绝明文样式表、
未知 CA 和错误 SAN。配置换代后 `10.0.2.99` 在 TCP open 前被拒绝，五次退出均恢复
121426 个空闲页、6 个任务和 4 个完成记录，N2 服务正常关闭。
本次复验覆盖隔离的静态 DNS、私有 CA 与 liteHTML 开发配置。

使用 [浏览器验收入口](../contracts/aurora_browser.md#controlled-https-guest-build)，
构建时打开 `--tls-resolve-net2`，系统构建时提供锁定的 `XOS_LWIP_SOURCE_ARCHIVE`。
客体容器用 `--network none --dns 127.0.0.1`。宿主已通过 HTTP parser 211 项和 4096
输入向量，系统 10 项许可材料检查通过，开放项为零。
