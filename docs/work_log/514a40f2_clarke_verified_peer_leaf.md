# ClarkE 原生 TLS 已验证叶证书

2026-11-27。基线 `8e66789c`，实现 `514a40f2`。原生 TLS 字节流在
X.509 和 DNS 名验证均通过后提供叶证书的 DER 借用视图。调用方要保留证书时，
应当在下一次流操作前复制字节。握手失败、致命 I/O 错误及正常完成后接口均返回
空视图。保留现有 TLS 1.3 配置、证书验证方式和 Net2 v2 协议。

## 构建及验收

以锁定 Mbed TLS 4.1.1 和经 GNU 源签名核对的 glibc 2.44 静态 SDK，
使用目标 GCC 16.2.0、Binutils 2.47、CMake 4.4.5 构建探针。
从同一源码重建带 lwIP 的普通 ISO，许可审计通过 10 项。
证书由宿主 OpenSSL 4.1.0 生成，测试端使用 Python OpenSSL 3.6.5，
QEMU 为 11.1.2。

```sh
python3 -B tests/native_tls_guest.py prepare --certificates build/peer-tls/certificates
python3 -B src/ports/native_tls/build_probe.py --archive "${MBEDTLS_ARCHIVE}" \
  --sdk "${GLIBC_SDK_BUILD}" --test-root build/peer-tls/certificates/tls_test_root.h \
  --output build/peer-tls/probe
XOS_LWIP_SOURCE_ARCHIVE="${LWIP_ARCHIVE}" \
  python3 -B scripts/build.py --output-dir build/peer-tls/system
python3 -B scripts/license_audit.py --build build/peer-tls/system
python3 -B tests/native_tls_guest.py test --system build/peer-tls/system \
  --probe build/peer-tls/probe --certificates build/peer-tls/certificates \
  --output build/peer-tls/guest
```

客体结果 `passed_subset`。两次独立 HTTPS 请求均校验 32 字节响应及双向
`close_notify`。客体计算的叶证书 SHA-256 与监听端实际提供的 DER 一致。
四个证书拒绝用例覆盖主机名错误、未知 CA、缺中间证书和过期，均取得空视图且未
发送应用请求。TCP 截断用例先取得已验证叶证书，随后读取失败且视图变空。探针另
检查首次握手前和正常完成后的空视图。每轮回到资源基线 `129525 / 4 / 2`。
禁用 RDRAND 的独立客体在程序入口前以 127 退出，监听端未收到连接。

| 工件 | SHA-256 |
| --- | --- |
| Mbed TLS 源包 | `3359a349e23db3d5536fcee032ae7b2ecbfc08972fab643089b5cbf2a375c98c` |
| glibc SDK manifest | `b490f9efeacaf75495ab3aa36489fc91e14bf9d4fe66f538b145bb21590e5961` |
| GNU 签名核验报告 | `81ca73e05129b0fd0dd6f7a2e286fb640521dde8b0a75286842848fbe0bccf0e` |
| 系统 `4cd26f879e6acc28` manifest | `160ff72feb2e1631f0e64fee77bd1d02202208739999e9e1c1607c1cd0f15602` |
| 系统 ISO | `df3a3f0f946d031d4c0f38692cd965097334454fe8a19fd9b4a0cfc0775f4c85` |
| 探针回执 | `6cc26cfa34df5d246637d4c0a867e12b40d268ae6eef5d702758e7dce5598d6b` |
| 探针 ELF | `5d66765dd04a09fabfaa2de11ec660f866a2d711a6ea6cec8fc785bf3899bafe` |
| 客体报告 | `1ce654a4339280b99aaef61621f351429061ed0245d9aef32fedfc4ce7ee0b88` |

WebCore 的网络加载链路接入时，应在借用期内将叶证书复制到响应对象拥有的
存储，并验证连接关闭后仍能读取摘要。此次范围为受控 IPv4 对端与本地 CA，
WebCore 装载、NetworkProcess、并发调用和生产 CA 仍待验收。
