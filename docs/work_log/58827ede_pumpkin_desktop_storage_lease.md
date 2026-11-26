# 58827ede · Pumpkin 桌面存储租约期限

#297 组合的桌面门在活动吊销场景首帧前失败。独立无桌面首次发放 19 项通过，原始失败
回执和黑帧继续保留。[#297 组合回执](../reports/pumpkin_first_account_post297_20261126/manifest.json)

在后续主线上为一次性诊断镜像加入阶段标记，并经 QEMU 只读读取这些数字。Display、
Interactium、持有者和真实 Mobius 均已就绪，26.766 秒观察到首帧。在七次正常管理
询问后，files 在客体单调时间 31.320 秒准确撤销私有存储端点。授予时间为 1.320 秒，
即此前固定的 30 秒期限。随后 Pumpkin 守护进程退出，持有者的下一次身份请求未发送，
私有操作者在发出吊销决定前收到失败回执。该证据确定了私有存储到期先于身份复核失败
的一条因果路径。#297 黑屏时没有记录同样的内部状态，历史早退仍保留独立的未确认原因。

修复在 `--pumpkin-mobius-elf` 已有构建配置中选择有界桌面租约。上限由 Pumpkin 普通
连接原有的 30 分钟和一分钟启动、退出预算推导。原有短操作配置继续采用 30 秒，
授权仍核验真实启动控制端、直接子进程和读写权限。控制端退出、端点关闭或设备故障仍
提前撤收，并清理未提交状态。宿主冻结时钟测试验证两种期限分别在准确边界成对关闭两个
端点，并立即响应控制端消失。[租约契约](../contracts/pumpkin_files_client_probe.md)

```sh
python3 -B tests/pumpkin_files_lease_host.py --sanitize
XOS_LWIP_SOURCE_ARCHIVE="$LWIP_ARCHIVE" python3 scripts/build.py --output-dir "$HEADLESS_SYSTEM" \
  --pumpkin-anchored-probe --pumpkin-native-login --pumpkin-user-login
python3 -B tests/pumpkin_user_login_guest.py --system "$HEADLESS_SYSTEM" --output "$HEADLESS_OUTPUT"
XOS_LWIP_SOURCE_ARCHIVE="$LWIP_ARCHIVE" python3 scripts/build.py --output-dir "$DESKTOP_SYSTEM" \
  --pumpkin-anchored-probe --pumpkin-native-login --pumpkin-user-login --pumpkin-mobius-elf "$MOBIUS_ELF"
python3 -B tests/pumpkin_mobius_guest.py --system "$DESKTOP_SYSTEM" --executable "$MOBIUS_ELF" --output "$DESKTOP_OUTPUT"
python3 -B tests/pumpkin_generation_authority_host.py
python3 -B tests/abi_doc_consistency.py
```

组合源码 `74e1d096` 基于 `67ee7b08`。该主线相对 #295 合并点新增的是 G4 文档和证据。
QEMU 11.1.2 的无桌面镜像 `0556a7ad4fd45012` 通过 19 项。桌面镜像
`cbb58a6d44324fb0` 通过 9 项，新增场景真实完成 37 次由账户持有者复核的轮询，随后
键盘切换主题并正常注销，代际保持。原有无信号注销和活动吊销分别在 1353 毫秒和
3010 毫秒确认，均完成资源回收。宿主代际 9 项、ASan/UBSan 租约检查及 ABI 对照通过。
验收沿用受控宿主配置及原已绑定的 Mobius ELF。物理可信启动和独立硬件代际保持待验收。
[租约到期观测、组合源码与真实客体回执](../reports/pumpkin_desktop_storage_lifetime_20261126/manifest.json)
