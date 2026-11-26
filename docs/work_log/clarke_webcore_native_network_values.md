# ClarkE · WebCore 网络地址值

锁定软件目标的 FrameLoader 编译单元曾在 `DNS.h` 找不到 `netinet/in.h`。
XOS 的 `IPAddress` 现在使用 4 字节和 16 字节的网络序值，解析普通 IPv4、完整或
压缩 IPv6，以及末尾嵌入 IPv4 的格式。WebCore 的地址比较、前缀长度和全零地址策略
沿用这些字节。Push 记录的长度字段直接从两个网络序字节读取。补丁按软件源锁
应用，GNU patch 零 fuzz 重放通过。

用生成的 WebCore 工具参数复编 FrameLoader 单元、`DNS.cpp` 和 Push 对应编译单元。
32 个数值及畸形输入在独立的 C++ 客体夹具中通过。第二份 ELF 链接真实
`DNS.cpp`、WTF 和 ICU，验证实际 URL 的 IPv4/IPv6 全零地址拒绝、回环、同族前缀和
跨族结果。两轮都在普通镜像 `8863999ce1a57285` 正常退出并精确回收。
域名查询队列和整页链接仍按各自目标推进。
[源码、目标对象和客体回执](../reports/clarke_webcore_native_network_values_20261127/manifest.json)
