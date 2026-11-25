# 网络会话代际隔离与 TCP 有序关闭加固

2026-11-25，基线 `5e49012ab2b359b31999d78083341ede98d5de4f`。
范围：PR #145 的会话复用、TCP close、请求 deadline 及定向测试评审。
分支 `codex/net-session-close-hardening-20261125`；与 glibc G1–G3 无源码依赖。

## 修改与兼容

1. `service_loop` 在 controller 撤销本轮已经处理过的应用后，旧 IPC 回复和端点仍可能
   留在已空闲的 core 槽位；直接接纳新应用会转发旧应用回复并遗失旧端点。
   现在每次接纳有独立、不回绕的内部代际号；复用前关闭旧双端点、清空整份 IPC 状态，
   回复仅使用匹配代际的绑定。解绑旧绑定不会误撤销刚接纳的新代际。
2. lwIP `tcp_close` 遇到尚未通过 `tcp_recved` 归还的接收窗口会发送 RST，并清除发送队列。
   现在未读环、拒收缓冲或未归还接收窗口均返回 `would_block`，完整保留 handle、数据和
   回调。应用读完后重试才进行有序 close；`cancel` 保持立即中止语义。
3. 锁定的 lwIP 2.2.1 已在 FIN 段内存不足时设置 `TF_CLOSEPEND`，返回 `ERR_OK` 并由
   定时器重试。保留该真实语义：成功后解除原应用回调，应用槽可复用；后续 FIN/RST
   不访问新应用状态。尚未建立的正常 close 使用 lwIP 自身关闭流程。
4. 服务在完整请求收到后重新采样单调时钟再调用 core，避免 NIC、其它会话或 IPC
   接收/抢占期间越过期限的 OPEN/SEND 使用旧时间授权。回复期限也取新样本判断。
5. TCP 环回归使用 997 字节不同相位报文、613/137 字节短读，保留未读后缀并实际覆盖
   两次跨 8192 字节环尾的分段复制。UDP 超长输入在空队列独立验证，再检查队列满。

没有新增 syscall、wire 操作号、字段、errno、公共类型或 newlib 私有依赖。
`net_service_v2.md` 明确 close 的读取后重试语义和内部代际生命周期。
`src/ports/lwip/README.md` 的通用启动说明在当前基线已是 `net-start <instance> raw`，
本次核对后保留已有修复。

## 先复现、后修复

新增 `service_loop_host.cpp` 实际链接生产 service_loop、core 与锁定 lwIP；夹具仅提供
内核 IPC/时间和设备调度边界。旧生产代码下以下三项真实失败：

| 场景 | 基线结果 | 修复后结果 |
|---|---|---|
| 已处理槽位撤销后立即换 PID 接纳 | 新应用收到额外的旧 OPEN 回复 | 只收到自己的 information，旧双端点各关闭一次 |
| ipc_recv 期间越过请求 deadline | OPEN 被执行 | timeout，零 handle，无后端 OPEN |
| RX 未读且 TX 已入队时 close | 返回成功，走错误关闭路径 | would_block，完整读回后 FIN，已接纳 TX 保留 |

另外两项在基线已经通过并保留为回归：耗尽真实 `MEMP_TCP_SEG` 后 FIN 定时器重试；
close 后复用连接槽时，迟到 TCP reset 不影响新 UDP 连接。没有模拟 tcp_close 返回值。

## 实际验证

持久证据：[network_hardening_20261125](../reports/network_hardening_20261125/verification.json)。
普通与 sanitizer 回执包含每个编译输入的实际 SHA-256，报告根 `manifest.json` 统一覆盖
回执和日志，Git 提交绑定该报告及代码。lwIP 归档按 `source_lock.json` 核验：
`83729c274c499d3348e9fbbe043a3113f3fa8953e7efddc7c21c7fcbb1f2b7b1`。

宿主 GCC/G++ 14.2.0（Debian 14.2.0-19）、Python 3.12.14。

```sh
python3 tests/net_service_host.py --archive "$XOS_LWIP_SOURCE_ARCHIVE" \
  --output build/net_hardening/normal_final
ASAN_OPTIONS=detect_leaks=0 python3 tests/net_service_host.py \
  --archive "$XOS_LWIP_SOURCE_ARCHIVE" --sanitize \
  --output build/net_hardening/sanitized_no_lsan
python3 scripts/verify_evidence_index.py docs/reports/network_hardening_20261125/manifest.json
python3 tests/check_public_evidence_paths.py --index --base 5e49012ab2b359b31999d78083341ede98d5de4f
```

- **passed**：生产 core + 真实 lwIP 23/23；生产 service_loop 2/2。
- **passed**：同样 25 项在 ASan + UBSan 下通过；`-fno-sanitize-recover=all`。
- **passed**：服务循环及 raw/native 入口的 freestanding、`-Wall -Wextra -Werror` 编译。
- **passed**：release `xos-glibc-sdk-preview` 的 `x86_64-elf-g++ 16.2.0` 对
  `service_core.cpp`、`service_loop.cpp`、`lwip_stack.cpp`、`net_service.cpp` 四个 TU
  做目标对象编译，使用 `-std=c++20 -O2 -Wall -Wextra -Werror -ffreestanding
  -fno-exceptions -fno-rtti -nostdinc++ -mno-red-zone -DXOS_NET_STACK=1`，包含当前源码的
  network/ports/shared/user headers、核验后的 lwIP `src/include` 及 preview
  `/opt/xos/sysroot/include`。该 preview 包附带的 sysroot headers 属现有 newlib profile；
  本模块只使用标准整数/内存接口，没有引入运行库私有耦合。

## 缺口和交接

- `ASAN_OPTIONS=detect_leaks=1` 的实际首次执行在 `--list` 阶段失败：宿主 ptrace
  环境阻止 LeakSanitizer。地址和 UB 检查完整执行，泄漏扫描需其他成员在允许环境用
  同一命令去掉 `detect_leaks=0` 后补跑。lwIP 使用固定内存池，逻辑资源回收仍由
  定向配额、撤销、关闭及真实客体资源检查分别验证。
- 本记录的 **guest_qualification=not_run**。客体验收由独立网络验收模块接入本提交，
  使用 preview 工具、`tests/net_transport_guest.py` 重建对应 SDK/镜像/fixture，补
  多应用、撤销后立刻复用、正常/异常退出、服务重启、资源归还和 TCP close 包级检查。
  该模块以新组合的实际回执独立交付，不沿用此前镜像结果。
- 正常关闭已由 lwIP 接管的 FIN/确认仍需远端及计时器推进。关闭成功表示本地接受，
  上层保留对端故障和未知交付处理；没有自动重放网络副作用请求。

## 后续审计：关闭中的实体 PCB 配额与停止回收

生产代码冻结为 `cf156b3443109fcb0d3da60107d1122b0b789f51` 后，进一步核对逻辑 handle
释放而 FIN 尚未确认的状态。新增一项真实池回归：应用 A 保持活跃连接，应用 B 连续
建立并关闭七个 TCP 连接且对端不确认 FIN，填满八个 PCB。B 再次 OPEN 得到 resources，
A 仍 connected；随后 core/stack shutdown 后可一次申请全部八个 `MEMP_TCP_PCB` 槽，
并完整归还。该结果在现有生产代码上已经正确，没有为此添加实现补丁。

源码对应关系：lwIP 2.2.1 `tcp_kill_prio` 只淘汰严格较低优先级；当前服务的 TCP
统一采用相同默认优先级。`netif_remove` 会经 `tcp_netif_ip_addr_changed` 中止接口上
仍在 active 链的关闭连接，所以服务停机也回收已经脱离应用 handle 的 FIN 状态。

新证据保持独立：[network_pcb_quota_20261125](../reports/network_pcb_quota_20261125/verification.json)，
未改写首批报告。实际执行以下命令，普通和 ASan/UBSan 各 **24 栈场景 + 2 生产循环场景通过**：

```sh
python3 tests/net_service_host.py --archive "$XOS_LWIP_SOURCE_ARCHIVE" \
  --output build/net_pcb_quota/normal
ASAN_OPTIONS=detect_leaks=0 python3 tests/net_service_host.py --sanitize \
  --archive "$XOS_LWIP_SOURCE_ARCHIVE" --output build/net_pcb_quota/sanitized
python3 scripts/verify_evidence_index.py docs/reports/network_pcb_quota_20261125/manifest.json
```

这是新增 host 资源审计，客体 exec/撤销/故障等资格继续由独立网络验收模块交付。
