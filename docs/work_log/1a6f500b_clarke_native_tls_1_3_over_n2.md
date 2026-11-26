# 1a6f500b · ClarkE Native TLS 1.3 over N2

2026-11-26。以 `7c581be6` 为基线，源码提交 `c7322fb2`。本轮交付
[独立开发配置](../../src/ports/native_tls/README.md)，用内核认证的既有 N2 IPC
和用户态 lwIP TCP 连接本地受控服务。TLS 位于调用进程内。调用方分别提供网络服务
进程身份、解析后的 IPv4 地址、待验证的 DNS 名和 DER 信任锚。静态程序用项目既有
HTTP 解析器核对完整响应，无新公共 ABI 或默认镜像配套改动。

[Mbed TLS 4.1.1 LTS 官方发布包](https://github.com/Mbed-TLS/mbedtls/releases/tag/mbedtls-4.1.1)
内含 TF-PSA-Crypto 1.2.0。发布包摘要按上游公布值核验，锁内另有原始许可文本
摘要。此配置在上游双许可中采用 Apache-2.0，登记原始声明并将同一文本纳入探针
输出。两个随包 framework 许可副本的字节相同。未改上游源文件。

上游默认配置从 `AF_INET6` 推断有 `inet_pton`。当前 XOS glibc SDK
暴露地址族但缺少该函数，显式选择 Mbed TLS 自带的文本地址解析器。上游内置时钟
与熵实现的宿主平台识别也不覆盖 XOS，因此使用上游适配点。证书时间读取
`clock_gettime(CLOCK_REALTIME)`，UTC 无效时证书校验失败。N2 I/O 使用独立的
单调时钟截止时间。TF-PSA-Crypto 的 CTR DRBG 使用经 glibc `getrandom` 取得
的内核熵作为种子，适配器处理短读和失败。验证模式始终为
`MBEDTLS_SSL_VERIFY_REQUIRED`，且握手必须产生零证书拒绝标志。

## 实际构建与客体

使用目标 GNU GCC/G++ 16.2.0、Binutils 2.47，宿主 CMake 4.4.5。clang 或兼容
宏不参与 TLS 目标构建。glibc SDK 来自已核验 GNU 签名的 2.44 源包，构建器核验
签名回执、sysroot 文件、七个目标工具摘要和两份 XOS 平台桥接源码。
以下为最终构建参数，宿主 OpenSSL 4.1.0 生成一次性证书，Python TLS 服务端使用
OpenSSL 3.6.5，QEMU 11.1.2 通过一次性 FAT 工作盘执行目标 ELF。

```sh
python3 -B tests/native_tls_guest.py prepare --certificates build/tls-input/certificates
python3 -B src/ports/native_tls/build_probe.py --archive "${MBEDTLS_ARCHIVE}" \
  --sdk "${GLIBC_SDK_BUILD}" --test-root build/tls-input/certificates/tls_test_root.h \
  --output /stage/probe
cp -a /stage/probe build/tls-probe-h
XOS_LWIP_SOURCE_ARCHIVE="${LWIP_ARCHIVE}" \
  python3 -B scripts/build.py --output-dir build/tls-system-h
python3 -B scripts/license_audit.py --build build/tls-system-h
python3 -B tests/native_tls_guest.py test --system build/tls-system-h --probe build/tls-probe-h \
  --certificates build/tls-input/certificates --output build/tls-guest-h
```

实构建生成三个 Mbed TLS/TF-PSA-Crypto 静态库及 x86-64 ET_EXEC。最终产物包含
上游 CTR DRBG、X.509 软件地址解析器、系统 `getrandom` 和 `clock_gettime`。
试验性的链接段裁剪曾令 SDK 的 `_init` 丢失 CRT 尾段，导致客体在进入
`main` 前故障。恢复常规 SDK 链接参数后，反汇编确认 `_init` 和 `_fini`
均有栈恢复和返回。首次有效 HTTPS 运行中，xsh 串口未启用退出状态跟踪，测试
未能收齐进程回执，最终运行开启该跟踪后逐项收齐。材料审计通过。

最终状态 `passed_subset`。普通客体使用 `qemu64,+rdrand` 及
`-rtc base=utc,clock=host`。每次交换记录绑定到该次连接的证书文件、SNI、
客体实时时钟和宿主时钟窗口。每次 guest UTC 取样均落在该次宿主窗口内。过期
叶证书的 `notAfter` 为 2026-11-25 07:24:17 UTC。

| 客体用例 | 结果 |
| --- | --- |
| 已受信根、正确中间证书、正确 DNS 名 | 握手使用 TLS 1.3 和 `TLS_AES_256_GCM_SHA384`，两次 GET 得到独立的 32 字节挑战响应，双方验证 `close_notify` |
| 主机名不符 | 证书标志 `0x04`，服务端收到拒绝告警，HTTP 请求为零 |
| 未受信签发者 | 证书标志 `0x08`，服务端收到拒绝告警，HTTP 请求为零 |
| 省略中间证书 | 证书标志 `0x08`，服务端收到拒绝告警，HTTP 请求为零 |
| 过期叶证书 | 证书标志 `0x01`，服务端收到过期告警，HTTP 请求为零 |
| TCP EOF 缺少 TLS 关闭通知 | 已认证的连接收到 HTTP 字节后，仍以 `MBEDTLS_ERR_SSL_CONN_EOF` 拒绝结果 |
| 独立 `qemu64,-rdrand` VM | 同一 ELF 在 glibc 启动阶段以状态 127 退出，宿主监听端未收到连接 |

每次普通连接后进程/IPC 资源回到 `129528 / 4 / 2`。时钟信任前提是开发宿主
提供的 QEMU UTC 时钟。缺熵运行核验的是完整应用启动门，未单独注入运行中的熵源
故障。公网 CA 与网站、生产时钟信任、物理熵源资格、并发调用方及 ClarkE
NetworkProcess 对接仍待验证。后续接入方可以复用此字节流，并在进程边界和来源
政策就绪后执行自己的受控端到端用例。

| 工件 | SHA-256 |
| --- | --- |
| 上游 Mbed TLS 包 | `3359a349e23db3d5536fcee032ae7b2ecbfc08972fab643089b5cbf2a375c98c` |
| glibc SDK manifest | `a4a6b3c278e34773088b11bb2a352d96487b9234755b9fcb9c7fe96ab9ace96e` |
| glibc GNU 源签名核验报告 | `8ec421dd86a6621729466788c3a3bed37283d12f9c1c207fb7bf283968885cf9` |
| 系统 `2d06377a9d86103b` manifest | `41dd4733afead2e81d96f6eca5313463e847c4cb59bb564c250acaa4784a3ff0` |
| 系统 ISO | `11dc63a0989fcce4a3e9596de49d604d689935f131d80b6ba5f7f739a247de90` |
| `build/tls-probe-h/receipt.json` | `3339012857e4e16515dc72bb3e136484e6e3cd8fa6a459d81097edf3bf6c3ba4` |
| 探针 ELF | `712e5560f38a3b79cd72db7bb7fef14108db7ef2de2a71349d28249ab3141571` |
| `build/tls-guest-h/report.json` | `d4e4eb2671b4f3bbfb996fe9c0ab451fa7b1ffb579a5186ae50c9f464ef35ecd` |
| `build/tls-guest-h/guest_serial.log` | `2dab9774496558b90d6de4f546b9963f0fb011c70cb59aeca80166b7763ab0f9` |
| `build/tls-guest-h/no_entropy_serial.log` | `369d831c2bd01fddb0c27f7e68a75656dc8f902a79c05f2026e5babece66af0b` |
