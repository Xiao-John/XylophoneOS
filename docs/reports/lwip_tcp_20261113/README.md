# lwIP TCP 受控客体纵切片

2026-11-13。N1 限定通过：QEMU user networking、静态 IPv4、单连接、用户态 VirtIO 原始帧服务和 lwIP NO_SYS raw TCP。未发布网络服务或 socket API。

```sh
python3 scripts/build.py
python3 scripts/build_lwip_tcp_probe.py --sdk build/sdk --archive /path/lwip_2.2.1+dfsg1.orig.tar.xz --output build/lwip_tcp_candidate
python3 tests/lwip_tcp_guest.py --system build --payload build/lwip_tcp_candidate/tcp_probe.elf --output build/lwip_tcp_candidate_guest
python3 tests/lwip_tcp_guest.py --system build --payload build/lwip_tcp_candidate/tcp_probe.elf --output build/lwip_tcp_candidate_guest_repeat
```

两次独立客体运行均通过：客体连接宿主临时监听端口，宿主精确检查请求并分两次发送新生成的 32 字节挑战；客体回显十六进制，宿主/客体验证完整相等，双向 EOF/关闭，探针资源恢复；无监听端口连接失败并回收；服务 reset/close 成功。分两次 send 不证明独立 TCP 段、丢包、重排或重传。初次尝试 TCP 数据和回收已通过，但脚本等待错误的 net-stop 输出标记而失败；随后修正脚本并重新构建、运行两次。

构建 `3a08a60368f9be90`；ISO SHA-256 `bf9511c456da0c7caf2e67ff8926edffd494f562f4f7f85d1641e82389bad957`；SDK 树 `7c0f7d332a02c57a72591375e830bb01d659b34a9a97a19c3d8fb27270605ba4`；ELF `862ddeb901329c13e09de5f045a14361ea55dad35bee4a31c16aaef8a5a462fa`；锁定 lwIP 源 `83729c274c499d3348e9fbbe043a3113f3fa8953e7efddc7c21c7fcbb1f2b7b1`。本机运行报告和原始串口位于各 build 输出目录；不把临时产物视为仓库中的冻结证据。

未覆盖：丢包/乱序/重传、压力、UDP、DHCP、DNS、TLS、生产熵、多应用并发与设备故障隔离；TCP 连接错误、超时和失败情况尚不等于完整 socket/POSIX 语义。见 [计划](../../plans/network_development.md)。
