# 242820a4 · Pumpkin 持久会话接入 Mobius

以主线 `16db86fa` 与实现 `242820a4` 在独立目录构建受控虚机 profile。复用持久账户、
独占 COM1、认证双向端点和真正的 Display/Interactium。启动器只在持有者提交有效的
钱包、核对完整的持久身份后启动桌面。从文件服务的同一个只读 pin 校验整个 Mobius ELF
再装载，桌面运行于普通进程权限。没有向桌面发送凭据、会话号或登记权限。
[会话入口契约](../contracts/pumpkin_user_login.md#mobius-登录)

```sh
XOS_LWIP_SOURCE_ARCHIVE="$LWIP_ARCHIVE" python3 scripts/build.py --output-dir "$SYSTEM" \
  --pumpkin-anchored-probe --pumpkin-native-login --pumpkin-user-login \
  --pumpkin-mobius-elf "$MOBIUS_ELF"
python3 -B tests/pumpkin_mobius_guest.py --system "$SYSTEM" --executable "$MOBIUS_ELF" --output "$OUTPUT"
```

Mobius ELF 与已验收的 xos.mobius 包载荷及独立 glibc 2.44 Widgets 构建回执一致。
使用锁定的 QEMU 11.1.2，镜像 `43ac38cb6cc72423` 通过五项。实际两个 800×600 帧显示
Midnight 与 Daybreak，经过多轮身份复核后 Ctrl+D 切换主题，Ctrl+Q 关闭桌面。
启动器确认注销后旧会话失效，空闲页、任务和完成记录恢复。宿主发送过的工作钱包在首帧
时已清空。同一凭据可以在另一轮重启时登录，持久吊销后被拒绝。另一受控工作盘上的
同尺寸改动 ELF 在真实认证后被拒绝，持久账户保留。
[客体回执、实际屏幕和工件摘要](../reports/pumpkin_mobius_session_20261126/manifest.json)

原有不含桌面的持久登录配置 `1aba162ecbe8bf41` 重建后通过全部 13 项，包括错误凭据、
文件权限、重启后吊销和不确定持久提交。身份核心与守护进程宿主测试通过。早期修改
验收驱动后的旧镜像按源绑定规则拒绝，最终回执来自重新冻结源码后的新镜像。

物理控制台的可信输入、物理独立代际、同一桌面会话的应用切换和权限委派、运行中
由管理端触发的吊销均需专项验收。
