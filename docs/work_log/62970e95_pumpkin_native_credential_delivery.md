# 62970e95 · Pumpkin 原生凭据交付

2026-11-26 · 主线基线 `217d3661`，经复验源码 `cbecdba7`。新增真实受信监督器、登记端、独立持有者、普通会话和封存资源的接入链。配置继续使用 files 私有槽和现有盘外代际记录。 [原生凭据契约](../contracts/pumpkin_native_login.md)

附加 `--pumpkin-native-login` 只随现有盘外开发配置使用。首次客体复跑到达代际初始化和读回，随后在持有者启动阶段报告状态 23，未创建账户。内核同时最多容纳八个进程，旧无界面流程保留了四个启动演示进程。新配置在交接 COM1 之前沿用现有演示进程收敛动作，启动独立持有者后完成全链路。状态通道携带有界非秘密阶段码。原配置只使用既有 0/1 结果。

```sh
XOS_LWIP_SOURCE_ARCHIVE="$LWIP_ARCHIVE" \
  python3 -B scripts/build.py --pumpkin-anchored-probe --pumpkin-native-login \
  --output-dir build/native-login-system
python3 -B tests/pumpkin_anchored_guest.py --system build/native-login-system \
  --native-login --slow-snapshot --output build/login-evidence/capacity-vm
python3 -B tests/pumpkin_host.py --sanitize
python3 -B tests/pumpkin_daemon_loop_host.py
python3 -B tests/abi_doc_consistency.py
```

源码、镜像、工具、配置、SDK 树和内置持有者工件由回执绑定。QEMU 11.1.2 单 CPU、512 MiB、无网络，每轮新进程及私有临时盘。工作盘在修订 2 暂停复制，实际暂停 8.212 秒，其中人为等待 7 秒。宿主代际记录从未纳入工作盘副本。

| 阶段 | 实际通过 |
| --- | --- |
| 首次登记 | 从真实登记端提交修订 1、2、3。由 sys63 生成凭据，通过父方认证端点送给独立持有者。错误凭据拒绝，正确凭据普通登录。持有者和监督器分别校验对端并清理凭据工作缓冲。 |
| 资源与撤销 | 未授予的连接、同账户的其他连接和复制会话均被拒绝。普通持有者读取登记接口被拒绝。登记端使用错误实际对端授予失败。正确授予后真实 files 封存对象返回四字节。普通注销后会话失效。吊销提交后旧身份查询、封存读取和旧凭据均被拒绝。 |
| 生命周期 | 独立持有者退出正常，原交付端点失效。监督器回收 daemon 和 holder 后比较空闲页、进程数及完成记录，计数相等。 |
| 正常复启 | 新 VM 读取盘外修订 3，登记端读回吊销；工作盘摘要保持一致，读操作没有推进代际。 |
| 旧盘恢复 | 使用修订 2 的盘副本和同一盘外修订 3，daemon 按原生存储检查停止；旧盘摘要保持一致。 |

宿主 ASan/UBSan、旧 daemon 循环和 ABI 表通过。新增私有帧检查覆盖旧配置拒绝新操作、填充校验、带截止时间的拒绝和重放。同一源码另建只启用 `--pumpkin-anchored-probe` 的镜像 `d1440c49c7b07af9`，原有三个全新 VM 阶段均通过。物理独立代际、交互登录、跨启动凭据保管与系统全量残留审计未验收。

| 工件 | SHA-256 |
| --- | --- |
| 系统 `e0271e93bc60c4eb` manifest | `c1a88d9affd5cab36dc4511ff2730d2579c0dda8ee45a7ac8a9e17b1b0d22369` |
| 系统 ISO | `5de430f5bf98e86377f52f0901982c1b4481f0b1b5fadcf22867308eae6ee319` |
| SDK 树 | `95ce47055a81434c8eb18afdff40c1861537388c2c7d01f00b9296d30dfe59b2` |
| 内置 holder ELF | `495dd36016b12ff40809d1c4ed44bc6ebc72c4a61fec94b685ac5ecedeb36740` |
| `build/login-evidence/capacity-vm/report.json` | `b50bb172779b9f95a9e0538acbef9078a08b229c3343eab3c9e456727596272f` |
| `build/login-evidence/capacity-vm/cycle_serial.log` | `5c430b23c9308187110533768349c69b44645809010906ae5dd179d1402826e8` |
| `build/login-evidence/stage-diagnostic/report.json` | `9d34cb7cea87417ed7113a476fd4b893ac2d838c3f4de5d1d7395b56599bea9a` |
| `build/login-evidence/host.log` | `4d15e083dbf6045936dba9f1adca776dc23cd4724ef694a8c5b1d221368ebe38` |
| `build/login-evidence/legacy-vm/report.json` | `72320088e1565c3b1cc8433805fb2a6ccb78bce5ec1354cb54c230070be0c42a` |
