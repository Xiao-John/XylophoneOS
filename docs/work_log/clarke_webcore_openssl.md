# ClarkE 的 WebCore OpenSSL 后端

XOS 软件 WebCore 配置要求同一目标 glibc C/C++ SDK 构建的静态 OpenSSL 3。
CMake 通过 `OpenSSL::Crypto` 接入上游密码算法和 PAL 摘要。`USE_OPENSSL`
为 EC 和 RSA 密钥启用上游平台容器。该配置只在显式启用 XOS 软件 WebCore 时启用。

基于锁定 WPE WebKit 2.54.2 原档重放 26 个 GNU patch 补丁，生成 2190 条 WebCore
编译命令。实际交叉编译了 18 个 OpenSSL WebCore 算法单元、PAL 摘要实现和夹具，
包括 EC、RSA 和 AES 系列对象。初次直接执行编译图中单条命令时 PAL 私有头导出
尚未运行。补跑同图的目标头生成步骤后，RSA 对象还暴露出 OpenSSL 3 的返回类型
变化。读取借用密钥的三个位置和模数长度助手改用 `const RSA*` 后，RSA 对象通过。
PAL 摘要沿用上游 OpenSSL 低层 SHA 接口，当前 OpenSSL 3.5.9 会输出弃用诊断。

PAL 夹具通过 `CryptoDigest` 分段写入 `abc`，验证 SHA-1、SHA-256、SHA-384 和
SHA-512 的已知结果。目标 ELF 使用同一版 OpenSSL，独立离线 Linux QEMU 上的
普通系统 `bdb3b5e6c3578aa9` 从 xsh 启动并退出 0。资源恢复为 `129709 / 3 / 1`。

运行前，用 CMake 输出的 `CryptoDigestOpenSSL.cpp` 编译命令编译夹具，目标链接
包含这两个对象、`libcrypto.a`、WTF、bmalloc 和目标 ICU 库。普通客体复用现有
静态 ELF 启动门。

```sh
python3 tests/qt6_sdk_probe.py --image "$SYSTEM_ISO" --payload "$PAL_DIGEST_ELF" \
  --marker 'XOS_WEBCORE_PAL_DIGEST_OK sha1 sha256 sha384 sha512 streaming' \
  --report "$PAL_GUEST_REPORT"
```

本轮验收覆盖算法目标编译和 PAL 摘要客体 API。完整 WebCore 链接、页面脚本中的
WebCrypto、同浏览器的 HTTPS 集成仍有各自的验收门。
[编译与客体回执](../reports/clarke_webcore_openssl_20261127/manifest.json)
