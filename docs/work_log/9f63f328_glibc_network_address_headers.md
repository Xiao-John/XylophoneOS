# 9f63f328 · glibc 网络地址头和字节序

## 范围与选择

CPython `_ssl.c` 的目标编译在包含 `<netinet/in.h>` 时终止，见端口账本 PL-0016。
从已验签的 glibc 2.44 安装其公共 `netinet/in.h` 和 generic `bits/in.h`，复用上游
`htonl`、`htons`、两个 `ntoh` 别名和 IPv6 地址常量。由已启用的 `socket` 构建目录
安装，保留原有精简子目录配置。六个公共符号在 XOS 当前的 `GLIBC_2.44` 版本节登记。

`sockaddr`、IPv4 和 IPv6 结构是目标程序的 libc 布局。`sin_addr.s_addr` 和端口对象
在内存中保存网络字节序。Net2 接收按网络阅读顺序解释的 IPv4 数值和整数端口，其
v2 报头仍按 XOS 现有的 little-endian 线格式序列化。例如 `10.0.2.2` 在
`sockaddr_in` 中是字节 `0a 00 02 02`，经 `ntohl` 变成 Net2 数值 `0x0a000202`，
在 Net2 报头中是 `02 02 00 0a`。结构体、字节序换算与访问权限属于不同层。
[Net2 契约](../contracts/net_service_v2.md)。

## 验收范围

使用锁定工具链，从签名 glibc 归档按正常 SDK 入口重建。独立编译严格 POSIX C11 和
GNU C++20 探针，断言结构体尺寸和偏移。两轮均须通过真正的四个字节序函数、IPv6
常量及分类宏。C++ 探针另外检验 Net2 的报头偏移和转换后的线上字节。运行门在隔离
FAT 盘回读静态 ELF、核验普通系统源和镜像清单，并在无网络 QEMU 中执行两个程序。
同一客体最后运行原有 newlib `libc_hello`，分别核对退出状态和资源回收。
C++ 测试通过实际目标 G++ 编译，并与同一 glibc C 库链接，覆盖公共 C 接口在 C++
调用方的布局和符号。完整 C++ 工具包重编及发布仍按独立门验收。

从签名源分别重建基线 `502cc673` 对应树和候选 SDK。候选新增两个头，原有 338 个已安装
头逐字节一致。静态库新增六个公开符号及两个 IPv6 内部别名，原有全局定义和 260 项
stub 清单全部保留。用最终 SDK 和从工作树重建的普通系统 `0b79c1fb64df9d14` 运行，
C 与 C++ 各退出 0，newlib 对照按契约退出 7，三轮均恢复 `129806 / 2 / 0`。
[ABI 差分](../reports/glibc_network_addresses_20261127/abi.json) ·
[客体回执](../reports/glibc_network_addresses_20261127/guest.json)。

完整共享构建遇到 `dl-sysdep.c` 中已有的动态解释器选择门。改用同一上游配置生成的
PIC 对象和 `libc.map` 独立链接，六个地址符号均导出为 `@@GLIBC_2.44`。这份 ET_DYN
证据覆盖版本映射，动态加载仍按 D1 的证据验收。
[PIC 符号](../reports/glibc_network_addresses_20261127/shared_symbols.txt)。

对 CPython 上游 `_ssl.c` 重跑目标语法检查后，最先缺失的是 `<netinet/tcp.h>`。
[目标编译诊断](../reports/glibc_network_addresses_20261127/ssl_parse.txt)。

在具备相应交叉工具的 Linux 环境，从仓库根运行以下命令。系统目录与其构建源树
分别传入，所有输出目录须为新路径。

```sh
out=build/glibc-network-addresses
python3 scripts/build_glibc_sdk.py --archive "$GLIBC_ARCHIVE" --output "$out/sdk-c" --jobs 6
python3 scripts/create_xypm_profile.py create --runtime-family glibc \
  --sdk-build "$out/sdk-c" --id xos-x86_64-glibc-network-addresses-v1 --output "$out/profile.json"
python3 tests/glibc_inet_addresses_guest.py \
  --sdk "$out/sdk-c" --profile "$out/profile.json" \
  --system "$ORDINARY_SYSTEM_BUILD" --system-source "$ORDINARY_SYSTEM_SOURCE" --output "$out/guest"
```

套接字、描述符生命周期、监听、真实 IPv6 网络、就绪等待、`_socket`、`_ssl` 和共享库
的专项验收顺序仍见 [网络与 TLS 交接](../plans/cpython_extensions.md#静态-openssl-与-_ssl-的交接边界)。
