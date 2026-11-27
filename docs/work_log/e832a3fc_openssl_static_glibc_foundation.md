# e832a3fc · OpenSSL 静态 glibc 底座

锁定 OpenSSL 3.5.9 LTS 和 Apache-2.0 许可。在无网络的 Linux 环境中完成签名校验、
交叉编译、头文件安装和静态链接。校验同时固定了 OpenSSL 主键 `B146647E…1692D40`
与签名子键 `C46ED3F2…DCCE71CB2`。OpenSSL 的熵桥调用 XOS glibc `getrandom`，
关闭依赖尚未实现的 POSIX `ucontext` 的异步路径。完整参数和复现命令见
[端口说明](../../src/ports/openssl/README.md)。

WPE WebKit 2.54.2 的 WPE 配置默认使用 libgcrypt。同一份上游源码包含 OpenSSL
的 WebCrypto 和 PAL 摘要实现，`CryptoKeyEC.h` 和 `CryptoKeyRSA.h` 提供该后端的
真实平台容器。此端口提供可供 WebCore 和 CPython 端口复用的头文件和归档。

## 独立普通客体

使用统一 `xos-x86_64-glibc-unified-cxx-v1` profile。普通 ISO 的 build id 为
`8863999ce1a57285`，宿主 QEMU 11.1.3。构建回执绑定 SDK、源码、静态归档和
无 `PT_INTERP`、无可写可执行段的探针 ELF。客体门额外核对 ISO 清单、构建时全部
系统源文件和 FAT 工作盘读取出的 ELF。两轮均无网卡。

| 客体 | 实测结果 | 退出码 | 资源 |
| --- | --- | --- | --- |
| 启用 RDRAND | `EVP_Q_digest` 命中 SHA-256 已知向量。两次 `RAND_bytes` 成功并返回不同字节。内存 BIO 上的 TLS 1.3 客户端验证临时 P-256 证书、收发应用数据、拒绝错误主机名。 | 0 | `129696 / 3 / 1` 前后一致 |
| 禁用 RDRAND | glibc 在调用 `main` 前因为启动熵不可用而拒绝，未进入 OpenSSL 随机数路径。 | 127 | `129696 / 3 / 1` 前后一致 |

初次禁用 RDRAND 的运行以为会进入 `RAND_bytes`，串口显示 glibc 更早拒绝启动。
客体脚本按真实启动契约修正了断言，使用同一 ELF 重跑两轮。GNU make 曾报告共享
文件系统 Makefile 时间偏差约 12 毫秒，随后完成归档、链接和两轮客体验证。
链接器仍报告 OpenSSL 终端 UI 路径的 `signal` 和 libc `abort` 的 `raise` 使用
未实现的入口，这些路径没有纳入验收。
[客体回执](../reports/openssl_static_glibc_20261127/guest.json)。

## 应用侧范围

真实 WebCrypto 尚需 WebCore 后端构建和客体 API 验收。CPython `_hashlib` 和 `_ssl`
尚未构建或运行。当前归档的套接字 BIO 禁用，生产 `_ssl`、壁钟兼容矩阵、系统 CA
管理和连网 TLS 继续按各自门验收。现有 ClarkE HTTPS 仍使用 mbedTLS。
