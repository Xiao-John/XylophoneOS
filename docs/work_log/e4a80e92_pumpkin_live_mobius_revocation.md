# e4a80e92 · 管理员吊销活动 Mobius 会话

在 `2a89b08f` 上冻结实现 `e4a80e92`。Mobius 登录可由受信宿主显式启用活动吊销。
现有受信启动路径固定账户，监督器继续以普通凭据持有者做身份复核。宿主同 UID 管理者
的 `SIGUSR1` 通过已认证的操作者代理交出一次吊销决定。登记端沿用现有账户吊销与
盘外代际提交。监督器撤收桌面、合成器和显示服务。原持有者核实已登录身份查询被
拒绝后退出。宿主确认持久代际恰好前进一次，监督器确认页、任务及完成记录均回收后
才报告成功。[私有协议和授权边界](../contracts/pumpkin_user_login.md#管理员吊销活动桌面)

```sh
XOS_LWIP_SOURCE_ARCHIVE="$LWIP_ARCHIVE" python3 scripts/build.py --output-dir "$SYSTEM" \
  --pumpkin-anchored-probe --pumpkin-native-login --pumpkin-user-login \
  --pumpkin-mobius-elf "$MOBIUS_ELF"
python3 -B tests/pumpkin_mobius_guest.py --system "$SYSTEM" --executable "$MOBIUS_ELF" --output "$OUTPUT"
XOS_LWIP_SOURCE_ARCHIVE="$LWIP_ARCHIVE" python3 scripts/build.py --output-dir "$LEGACY_SYSTEM" \
  --pumpkin-anchored-probe --pumpkin-native-login --pumpkin-user-login
python3 -B tests/pumpkin_user_login_guest.py --system "$LEGACY_SYSTEM" --output "$LEGACY_OUTPUT"
```

QEMU 11.1.2 的发布候选 `e9481e988cda2385` 通过 7 项。真实 Midnight 与 Daybreak 帧、
普通关闭和原账户再次登录均通过。同一安装内另一轮启动显示真实桌面后，向操作者 CLI
发出 `SIGUSR1`，在 2689 ms 后确认持久吊销、原会话拒绝和资源回收。原账户之后启动
失败，另一账户仍可登录，独立吊销仍可用。安装了同尺寸改动 ELF 的另一张工作盘继续
拒绝桌面启动。无桌面镜像 `39354711116f4039` 在同一提交重建并通过原 13 项。宿主
ASan/UBSan、x86-64 freestanding 编译和 ABI 对照均通过。
[源码树、镜像、Mobius SDK、初次失败和客体回执](../reports/pumpkin_live_mobius_revocation_20261126/manifest.json)

早期两次观察中，正在启动的桌面提前退出，原有冻结镜像也有同类表现。独立诊断确认一次
未收到凭据持有者的周期复核回复，原因未确认。正式验收逐次独占运行 QEMU，观测脚本
在每次截屏后释放 QMP 连接，避免掩盖进程退出状态。首轮及历史回放的失败回执原样保存，
原始错误日志摘要纳入索引。单独补测启用管理模式但一直不吊销的退出流程时，QMP 套接字
在首帧前消失，未取得该组合的独立回执。

权限仍限于已有开发安装和受信宿主。物理管理席位、生产独立代际、跨应用授权和正式发行
仍需验收。
