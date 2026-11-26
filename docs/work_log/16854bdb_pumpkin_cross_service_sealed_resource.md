# 16854bdb · Pumpkin cross-service sealed resource

2026-11-26。基线 `c4ac7cdb` 已含 #245 的宿主管道登录。受测源码与公开提交
`8f2ea812adb4252e962ff69cea30cd1f4f78292b` 的 Git 树
`6a970f6ef4f618ee378cf3b546441d103870af7f` 一致。复核已保留的
[用户登录](317b1813_pumpkin_operator_login_across_reboots.md)、
[普通镜像封存对象](8ca1f149_pumpkin_sealed_resource_guest.md) 与
[盘外代际快照验收](31dde03e_pumpkin_anchored_guest_snapshot_fence.md) 后，选择补齐
守护进程和独立对象服务之间的授权。原普通镜像封存 fixture 在 broker 进程内持有
易失账户核心。原专用登录配置在 daemon 内持有封存对象。这次通过真实独立
`pumpkind` 与 broker 进程检查同一次资源操作。

受信启动者核验两条启动链。只有 daemon 的真实登记端可以接纳 broker 自建的
专用 IPC 对。普通端点申请有两秒期限的一次性关联，绑定发起 PID、认证端点、
会话、已登记 broker 及其连接编号。broker 从自己的 files 会话取得封存对象并
保留打开描述。它在读之前用本地解析出的对象键、所有者与内核核定的客户端对端
请 daemon 授权。daemon 消耗匹配的关联并用现有 `authorize_owner` 校验。最终
读取留在 broker，普通调用者只收到字节或空拒绝。专用线使用现有 sys84–86，
应用及系统默认入口沿用原 ABI。 [资源服务契约](../contracts/pumpkin_resource_service.md)

## 真构建与回归

使用 GNU GCC/G++ 16.2.0、Binutils 2.47、QEMU 11.1.2 和同镜像 SDK 构建的
dash 0.5.13.5。所有虚机使用一次性工作盘，普通资源镜像不启用私有尾区、
持久 Pumpkin 或独占串口配置。

```sh
python3 -B scripts/build.py --output-dir build/bridge-system
python3 -B scripts/build_pumpkin_daemon.py --bridge-probe \
  --sdk build/bridge-system/sdk --output build/bridge-fixture
python3 -B scripts/build_dash.py --sdk build/bridge-system/sdk --receipt build/bridge-dash.json
python3 -B tests/pumpkin_daemon_guest.py --bridge-probe --system build/bridge-system \
  --fixture build/bridge-fixture --dash-receipt build/bridge-dash.json --output build/bridge-guest
python3 -B tests/pumpkin_host.py --sanitize --target-cxx x86_64-elf-g++ --output build/bridge-core-host
python3 -B tests/pumpkin_daemon_loop_host.py
python3 -B scripts/license_audit.py --build build/bridge-system
```

xsh 与 dash 各完成一轮分进程协议。从另一真实进程提交与其 broker 连接编号相符的
关联，daemon 仍按原真实发起者拒绝。另有同 PID 错连接、重复、过期、另一
有效账户、正常注销、原始认证连接关闭、broker 更换及真实登记吊销。拒绝响应
不带对象字节。broker 更换后，当前拥有者仍可通过新连接读取。daemon 退出时，
broker 在父控制端仍打开的情况下自行回收。两次资源计数均恢复
`[129711, 3, 1]`。同镜像另用未开启 bridge 的常规 P1 和原封存对象 fixture
复验。宿主 ASan/UBSan、目标 freestanding 编译、原回复时限检查和许可材料审计通过。

兼容性另外使用相同提交的 `--pumpkin-anchored-probe --pumpkin-native-login
--pumpkin-user-login` 镜像复跑 `tests/pumpkin_user_login_guest.py`。实际 QEMU
覆盖凭据领取、同一凭据在新 VM 成功登录并注销、持久吊销后新 VM 拒绝，以及
未确认发布和用户文件同步失败时不重复发放。日志只保留 case 和退出结果。
独立 `--pumpkin-anchored-probe` 镜像同时复跑
`tests/pumpkin_anchored_guest.py --slow-snapshot`，盘外代际发布后暂停 QEMU 注入
七秒等待再快照；本次暂停窗口约 8.19 秒。登记并吊销、正常新 VM 恢复、旧盘拒绝
三个启动阶段均通过。

| 工件 | SHA-256 |
| --- | --- |
| 普通系统 `ca2bea400dcb4ce8` manifest | `b28c1e4ace15848e8da42966c3efc17cb6d1222c08fd0b93feda4fb6c81e8484` |
| 普通系统 ISO | `67443ba128db1f89022ce31febf826c363d56e23fd89c65059b0a28cf9845d4a` |
| SDK 树 | `4538dddb265610823365155fac180a12ef4dd27d2dea7a189e64edae14c5d7cf` |
| `build/bridge-fixture/receipt.json` | `ae108a067fc05c44f04112853513fc35137f1e928a81f489df32222c3f43643a` |
| `pumpkind.elf` | `6aa02b7c61ed57db5d3b99db5a07acc98557432fbaa0a3aed3f33122f7688200` |
| `pumpkin_sealed_broker.elf` | `02c12c810e64eacfeae5a6662b15244eafe9f5ce5069b106b80fdd6e0a05f958` |
| `build/bridge-guest/report.json` | `98c35a99150fb6f89055d6a26e1880abb448ebda1c7a898edeee83e270f3ee3b` |
| `build/bridge-guest/guest_serial.log` | `93336426a4b9038133d70f6c0f206851c6d87aac0495dc3b72e18b9a83d7ea1c` |
| `build/bridge-legacy-p1-guest/report.json` | `f276b1ed1e9c46cd72139f8302737a14dc69d1b9fb33960c62390ab78e071a05` |
| `build/bridge-legacy-resource-guest/report.json` | `95bb6bf51467e6127ba8ff14c3a78771999dd68c91a3249a779e8c0743063b7e` |
| 用户登录系统 `08c78ee1ae69a382` manifest | `e94dc62fdcc1f96df7899cc51845878640c6ede026f70d33297e65bce6f38269` |
| `build/bridge-login-guest/report.json` | `b21684e89fe7f28fa26a2e80cb51eac3fc0b1f2e8c8125df5a3c9555ece9f1b2` |
| 盘外代际系统 `02c139305cf262bb` manifest | `b1252a3501ea5c289278f7bda30a23accfbcaacc34d42c2a0de40ec3569ff0c0` |
| `build/bridge-anchor-guest/report.json` | `2306272c994715ca00e519a19d01c49e491e0ed8c7e01590ad8b57871d84895b` |

## 尚待部署验收

跨服务读取已通过普通镜像的明确易失配置。持久登录与盘外代际采用另外的 QEMU
开发配置。现有设备及测试配置中未找到可供正式接入的独立硬件 NV。物理掉电后的
代际、可信物理输入、挂接真实已登记用户的常驻资源部署，以及命名 FAT 对象跨启动
保留所有者仍需各自验证。后续可把同一次读取授权接到已登记用户的可信启动链，
按实际设备和部署配置重做组合验收。
