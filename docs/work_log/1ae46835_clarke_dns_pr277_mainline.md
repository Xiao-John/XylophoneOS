# 1ae46835 · ClarkE DNS 在 #275 后的主线复验

2026-11-26 · 从实际主线 `b93caa08` 迁入 ClarkE 受控 HTTPS 的 net2 解析七个提交。
该基线含 DNS referral 分类修正和按宿主 OS、架构隔离的 FAT helper 缓存。原两套
验收回执的字节保持在各自索引。此分支交付显式启用的 `--tls-resolve-net2` 开发构建。
[原独立验收](ff907778_clarke_net2_dns_mainline.md)

从源码 `1ae46835` 重建使用 `--net-dns-probe` 的系统 `dced7bab7f4a7907`。复用锁定
的 glibc SDK/profile 及 Qt Widgets 归档，重新编译 ClarkE 和 TLS、打包 XPK。在
无外网的 ARM64 Linux 容器里用 QEMU 11.1.3 运行原 `tests/clarke_https_guest.py`，
D3 测试服务、局部 DNS 与测试 CA 沿用现有入口。
[复验回执](../reports/clarke_dns_post_275_20261126/manifest.json)

原六项客体断言全部通过。安装后的 ClarkE 核对 HTML、同源 CSS 和 BMP 的响应摘要，
800×600 图像中样式背景、前景及 BMP 的颜色像素分别为 226673、1501、1024。
对端收到六次预期 SNI、四个带正确 HTTP Host 的请求和四次双向 TLS 关闭。浏览器明确
拒绝明文样式表、未知 CA 和错误 SAN。配置换代后的 `10.0.2.99` 解析结果在 TCP open
前被拒绝。五次退出都恢复 121426 个空闲页、6 个任务和 4 个完成记录，N2 返回 `close=0`。
本次验收使用隔离静态 DNS、私有测试 CA 和 liteHTML。

宿主 HTTP parser 通过 211 项检查与 4096 个输入向量。N2 客户端、跨宿主 work disk
缓存检查、XYPm 私有缓存检查通过。系统许可材料检查共 10 项，开放项为零。
[构建和复验入口](../contracts/aurora_browser.md#controlled-https-guest-build)
