# ClarkE 的 XOS 域名解析队列

在已锁定的 WebCore 软件目标上，`native_dns_queue.patch` 将 WebCore 的域名查询
接到现有 Net2 用户态服务。网络进程在 WTF 主循环初始化后使用
`configureXOSDNSService` 传入其启动方提供的服务 PID。同一进程可重复设置同一个
PID，服务重启时由启动方重新创建持有网络访问权的进程。连接校验两个 IPC 端点的
对端身份，再提交原生 A 查询。

队列使用单个 WTF 工作线程和最多 24 个待完成请求。3 秒截止时间从入队开始，
完成回调在主线程执行。预取沿用 WebCore 的合并逻辑和同一原生查询。取消移除活动
请求并回调一次，工作线程观察取消后释放 Net2 票据。结果通过请求身份检查后再交付，
允许调用方复用已取消的编号。

[原生 Net2 DNS 契约](../../../../docs/contracts/net_service_v2.md)

## 客体验收

在 XOS 目标上链接夹具 `tests/fixtures/webkit/xos_webcore_resolver.cpp`、
`DNS.cpp`、`DNSResolveQueue.cpp`、`DNSResolveQueueXOS.cpp`、WTF、bmalloc 和 ICU。
XOS 预取定时器使用同一 WTF 主循环。链接回执绑定实际 ELF、夹具、软件源锁和用到的
三个 Net2 头。传入与原生 DNS 探针镜像一致的系统源码目录。

```sh
python3 tests/webkit_native_dns_guest.py --system "$NET_DNS_SYSTEM" --elf "$RESOLVER_ELF" \
  --receipt "$LINK_RECEIPT" --webcore-source "$XOS_ROOT" \
  --system-source "$SYSTEM_SOURCE" --output "$RESOLVER_TEST_OUT"
```

普通 QEMU 镜像 `c8afe20db9c3005d` 验证了实际 A 查询、NXDOMAIN、一次取消回调、
编号复用、错误 PID 和正常停机后的拒绝。FAT 回读与已链接 ELF 的摘要一致。捕获
的三个 DNS 问题对应受控场景，退出后资源恢复到 `129690 / 3 / 1`。
[链接、客体和数据包回执](../../../../docs/reports/clarke_webcore_net2_resolver_20261127/manifest.json)
