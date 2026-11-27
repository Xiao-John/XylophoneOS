# 61202e5f · glibc 经 Net2 出站 TCP

2026-11-27 · 静态 glibc 增加阻塞 IPv4 TCP。应用通过现有描述符、已认证的用户态 Net2
IPC 和 lwIP 收发。受信静态安装配置由 Xsh 交付服务 PID，客户端核对两个 endpoint
的 PID。现有目标 ACL、Net2 v2 消息布局及启动描述符布局沿用原契约。
[实现边界与后续计划](../plans/glibc_net2_socket.md)

## 客体验收

- 受信静态镜像 `93258aa20d07a27d` 和固定 glibc profile 由 QEMU 11.1.3 验收。
  两次启动服务获得不同 PID。每次完成两轮独立的宿主 TCP 挑战。客体验证 32 字节随机
  应答，核对对端停止发送后的 EOF，继续完成 1537 字节短写循环。对端逐字节核对
  请求及尾部数据，并收到最后一个描述符关闭产生的 EOF。
- 客体覆盖描述符容量和复用、重复连接、文件类型、`CLOEXEC`、dup、
  fork 拒绝及半关闭与非阻塞操作的明确错误。缺少服务、服务 PID 不符、目的地址
  被拒以及闭端口分别返回预期错误。每个用例恢复原资源计数。在服务运行时为
  129615 空闲页、3 个任务及 1 个完成记录。每轮停网后恢复 129787、2、0。
- 普通镜像 `6ee274714e525f50` 通过既有原生 Net2 端到端回归，包含 HTTP、UDP、
  TCP、四个并发应用及两个受控窗口的有序关闭用例。相同 glibc SDK 在该镜像运行
  既有 C 和 C++ 地址布局与字节序测试，以及原生 libc 启动对照。
- 签名验证后的 glibc 静态归档保留基线 3713 个全局已定义符号的名称和类型，
  增加八个私有桥接符号。Linux 宿主的 files、扩展 files、terminal 回归分别通过
  15、8、27 组。系统许可材料检查通过 10 项。

验收绑定到 `61202e5f`，基线为 `8e66789c`。对后续主线 `0227427a` 复核了
Mobius #345 和原生 TLS #346 的变更，路径无重叠且 Git 合并树生成成功。客体回执仍绑定
原测试树。同进程多连接的并发调度与中途服务失联注入留待后续验收。
DNS、套接字选项、半关闭、poll、IPv6 联网和入站服务另有实现门槛。
[回执与摘要索引](../reports/glibc_net2_socket_20261127/manifest.json)

## GNU 共享重链回归

在同一源码树重新验签展开 glibc，按已有 D1 流程构建 GNU PIC 归档、解释器和含
XOS PIC 支持对象的 `libc.so`。GNU 构建纳入 `socket` 子目录并重编
`xos_net2_socket.os`。ELF 符号表核对四个公开 API 均定义在 `GLIBC_2.44`，
Net2 私有桥接符号全数解析为本地定义。

使用新链出的解释器和 libc 在普通镜像复跑现有 D1 C 入口。构造、环境、auxv、文件读取、
关闭和 TLS errno 检查通过，退出状态为 0，运行前后同为 129696 空闲页、3 个任务、
1 个完成记录。本回归覆盖私有 D1 C 动态入口，动态 TCP 数据收发和共享 C++ 另行验收。
[共享构建和客体回执](../reports/glibc_net2_socket_20261127/shared_d1_c_guest.json)

## 复验

选择同一套目标 GCC 和 binutils。用锁定的 glibc 与 lwIP 归档执行下列命令。
受控对端可在隔离容器的 loopback 上运行。

```sh
python3 scripts/build_glibc_sdk.py --archive "$GLIBC_ARCHIVE" --output "$SDK"
python3 scripts/create_xypm_profile.py create --runtime-family glibc --sdk-build "$SDK" \
  --id xos-x86_64-glibc-net2-ipv4-tcp-candidate --output "$PROFILE"
XOS_LWIP_SOURCE_ARCHIVE="$LWIP_ARCHIVE" python3 scripts/build.py --output-dir "$TRUSTED_SYSTEM" \
  --quiet-demos-on-launch --net-static-profile docs/reports/n4_static_profile_20261126/profile.json
XOS_LWIP_SOURCE_ARCHIVE="$LWIP_ARCHIVE" python3 scripts/build.py --output-dir "$ORDINARY_SYSTEM" \
  --quiet-demos-on-launch
python3 tests/glibc_net2_tcp_guest.py --sdk "$SDK" --profile "$PROFILE" \
  --system "$TRUSTED_SYSTEM" --output "$TCP_EVIDENCE"
python3 tests/glibc_inet_addresses_guest.py --sdk "$SDK" --profile "$PROFILE" \
  --system "$ORDINARY_SYSTEM" --system-source "$PWD" --output "$INET_EVIDENCE"
python3 scripts/build_net_transport_probe.py --sdk "$ORDINARY_SYSTEM/sdk" --output "$NATIVE_PROBE"
python3 tests/net_transport_guest.py --system "$ORDINARY_SYSTEM" \
  --payload "$NATIVE_PROBE/net_transport_probe.elf" --output "$NATIVE_EVIDENCE" --serial-only
```

D1 回归依照[已链接解释器路径](glibc_d1_linked_interpreter.md)重建 GNU PIC 和共享
组件。使用带匹配构建回执的 dash，选择 `tests/glibc_d1_linked_interpreter_guest.py`
的 `--case c`，传入上述普通镜像、静态 SDK 及新生成的 GNU 构建目录。
