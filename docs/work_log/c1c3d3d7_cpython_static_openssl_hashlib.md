# c1c3d3d7 · CPython 静态 OpenSSL hashlib

CPython 3.14.9 的 glibc 构建新增可选 `--openssl-build`，消费已经校验签名并与同一 SDK
绑定的 OpenSSL 3.5.9 归档、头文件和许可。实际 `_hashlib` 配置探针将调用带入静态
链接，借助同一链接组中的 `libcrypto.a` 及 glibc 解析其符号。保持普通构建的默认
依赖与已有 zlib 开关。当前交付范围为独立静态 CLI 探针，发行 XPK 仍沿用原组合。

## 验收

统一 profile 为 `xos-x86_64-glibc-unified-cxx-v1`。产出 x86-64 静态 ELF；`_hashlib`
编入解释器。普通无网络 QEMU 客体通过原启动、时钟、线程探针，以及经 `_hashlib`
的 SHA-256、HMAC、PBKDF2、scrypt 已知向量和未知算法拒绝。两进程均正常退出，资源
回到启动后的基线。错误 SDK profile 绑定在构建前被拒绝。同一 ELF 在独立旧普通
系统 `8863999ce1a57285` 及 #335 合并树的普通系统 `bdb3b5e6c3578aa9` 各运行一次。
两轮资源基线分别为 `129793 / 2 / 0`、`129806 / 2 / 0`。
默认参数的独立配置复验使 `_hashlib`、`_ssl`、`_socket` 均保持 `missing`。两种
配置都选择 `dynload_stub.o`。默认配置未重复交叉编译和运行客体。
[客体回执](../reports/cpython_static_openssl_hashlib_20261127/guest.json)。

最初的跨编译尝试发现宿主解释器编入了固定的标准库路径。复用原构建卷时使用匹配的
挂载位置后，版本探针通过。CPython 的配置脚本将 OpenSSL 归档置于已有静态 `LIBS`
之后，首次 `_hashlib` 链接检查因此无法解析 glibc 符号。把匹配的 `libcrypto.a`
纳入现有 SDK 链接组后通过正式检查及构建。

## `_ssl` 编译阻塞

使用同一份已生成的 `pyconfig.h` 和目标 SDK，直接把原上游 `Modules/_ssl.c` 送入
目标编译器做语法检查。首条诊断为 `Modules/socketmodule.h:10:11` 缺
`<netinet/in.h>`。另查上游 `_ssl` 的 fd 分支依赖 `SSL_set_fd`，而当前 `no-sock`
归档只提供内存 BIO 路径。构建配置将 `_ssl` 保持 `missing`，客体确认它未编入。
`socket/connect/recv/send/poll` 仍是 SDK stub，`_socket` 同样未编入。现有 Net2
以 PID 验证的用户态会话提供 IPv4 TCP 和 DNS；POSIX fd、就绪等待及生命周期按
[分步依赖](../plans/cpython_extensions.md#静态-openssl-与-_ssl-的交接边界)推进。
[目标语法检查](../reports/cpython_static_openssl_hashlib_20261127/ssl_parse.txt)。

## 复验入口

在匹配 SDK 工具链的 Linux 环境，使用锁定 CPython 归档、同版本宿主解释器，以及
[已验 OpenSSL 构建](../../src/ports/openssl/README.md)。普通系统目录与其原构建源树
分别传入。输出路径须为新目录。

```sh
python3 scripts/build_cpython.py --archive "$CPYTHON_ARCHIVE" \
  --sdk "$UNIFIED_KIT/sdk" --glibc-profile "$UNIFIED_KIT/profile.json" \
  --openssl-build "$OPENSSL_BUILD" --build-python "$BUILD_PYTHON" \
  --output-dir build/cpython-openssl/cli --compile-probe

python3 tests/cpython_glibc_guest.py --archive "$CPYTHON_ARCHIVE" \
  --sdk "$UNIFIED_KIT/sdk" --glibc-profile "$UNIFIED_KIT/profile.json" \
  --openssl-build "$OPENSSL_BUILD" --cpython-build build/cpython-openssl/cli \
  --system-build "$ORDINARY_SYSTEM_BUILD" --system-source "$ORDINARY_SYSTEM_SOURCE" \
  --output build/cpython-openssl/guest
```
