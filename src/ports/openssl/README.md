# XOS glibc 静态 OpenSSL

此端口用统一 glibc SDK 构建 OpenSSL 3.5 LTS 的目标静态归档。`prefix/usr`
包含 `libcrypto.a`、`libssl.a`、配套头文件和 pkg-config 元数据。`prefix/LICENSE.txt`
保留上游 Apache-2.0 许可。源码归档、独立签名、发布密钥集合和端口输入都由
`source_lock.json` 固定，构建会核对上游签名的主键与签名子键。

目标配置沿用 OpenSSL 上游的 pthread 支持及 x86-64 汇编。随机数依赖 XOS glibc
`getrandom(…, 0)`。OpenSSL 的平台熵入口传递该调用的真实结果。当前配置包含
默认 provider、同步密码操作及内存 BIO。异步执行、套接字 BIO、数据报、QUIC、
可加载 provider 和 secure heap 均禁用。应用须通过各自的验收才能宣告 WebCrypto、
CPython `_ssl`、网络 TLS 或系统信任库可用。现有 ClarkE 的 mbedTLS 传输路径保持原有配置。

## 构建与客体复验

在安装了 SDK 绑定的目标 GCC/binutils、GNU make、Perl、`patch`、`gpgv` 和 Python 3.11+
的 Linux 环境中，从项目根目录运行。三个发行输入变量分别指向锁定的归档、签名和公钥集合。

```sh
python3 scripts/build_openssl_target.py \
  --archive "$OPENSSL_ARCHIVE" --signature "$OPENSSL_SIGNATURE" \
  --release-keys "$OPENSSL_RELEASE_KEYS" \
  --sdk "$UNIFIED_KIT/sdk" --profile "$UNIFIED_KIT/profile.json" \
  --output build/openssl-target/verified --jobs 6

python3 tests/openssl_target_guest.py \
  --build build/openssl-target/verified \
  --sdk "$UNIFIED_KIT/sdk" --profile "$UNIFIED_KIT/profile.json" \
  --system "$ORDINARY_SYSTEM_BUILD" --system-source "$ORDINARY_SYSTEM_SOURCE" \
  --output build/openssl-target/guest
```

两个输出目录须为新路径。客体门需要 `qemu-system-x86_64` 和宿主 C++ 编译器，
在独立 FAT 工作盘验回 ELF，再在无网络的普通 ISO 中分别启用与禁用 RDRAND。
报告绑定实际端口源码、静态归档、探针 ELF、SDK/profile 和系统清单。

上游发行签名和发布密钥见 [OpenSSL 发布页](https://www.openssl-library.org/source/)。
