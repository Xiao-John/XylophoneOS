# 317b1813 · Pumpkin 用户凭据跨虚机登录

2026-11-26 · 基线 `78f014b6`，实际构建源码 `683a6341`。专用开发入口使用真实发放、盘外代际和独立普通持有者。用户自行选择宿主凭据文件保存和提交。 [使用与授权范围](../contracts/pumpkin_user_login.md)

XOS 普通终端虽能无回显并限制应用读写，既有终端会话和 sys80 不能认证一般应用所显示的登录提示。复用已验收的 COM1 独占交接，使用专用宿主管道和独立凭据帧。交接前丢弃启动文本，原有串口测试捕获器在启动前拒绝该镜像。用户状态、凭据工作区和 QMP 路径均在私有宿主目录。正式物理代际、物理输入提示的信任、宿主文件加密和持续桌面登录保持未验收。 [终端契约](../contracts/terminal_control.md)

```sh
XOS_LWIP_SOURCE_ARCHIVE="$LWIP_ARCHIVE" \
  python3 -B scripts/build.py --pumpkin-anchored-probe --pumpkin-native-login \
  --pumpkin-user-login --output-dir build/user-login-system
python3 -B tests/pumpkin_user_login_guest.py --system build/user-login-system \
  --output build/user-login-evidence/final-vms
python3 -B tests/pumpkin_host.py --sanitize
python3 -B tests/pumpkin_daemon_loop_host.py
python3 -B tests/abi_doc_consistency.py
```

实际 QEMU 11.1.2，单 CPU、512 MiB、无网络、每轮新虚机进程。正常登记之后由另一宿主进程提交同一文件，在全新虚机中登录、核对账户身份、正常登出和验证会话失效。错误凭据和吊销后同一原凭据均在全新 VM 经真实普通认证被拒绝。正常登录和每次拒绝不改变盘外代际。吊销由原有登记端提交修订 3。用户作用域内的凭据文件登录前后保留同一 inode 和修改时间。

| 失败情况 | 实际观察 |
| --- | --- |
| 新安装的目标文件已存在 | 在启动 VM 与发布之前拒绝，文件内容和空代际保持原样。 |
| 符号链接、多链接和 0644 文件 | 凭据描述符检查拒绝。 |
| 修订 2 持久提交，但故意向真实客体回复结果未知 | 真实守护进程未发放凭据，目标文件保持 0 字节。再次登记拒绝，没有创建第二份文件，盘外状态仍为同一修订 2。 |
| 用户凭据文件写完后注入同步失败 | 工具未确认发放，保留私有文件及已提交的真实修订 2。再次登记拒绝，没有创建第二份文件。 |

正常路径使用五个新 VM，失败注入另启两个。验收报告只保存源码及工件身份和检查状态。客体凭据帧、命令输出和私有用户文件未纳入测试工件。宿主 ASan/UBSan、守护循环和 ABI 表检查通过。相同源码另建只启用原有 native-login profile 的 `ba90cf737ced2dde`，原来的 cycle、healthy、stale 三次新 VM 全部通过。

| 工件 | SHA-256 |
| --- | --- |
| `2540640eecba8248` 系统 manifest | `af43b9f72cbb47907f0953a1c0ad59a21ef277f75ebbd7cdc14dc25067663127` |
| 系统 ISO | `e83aad53d1a049b9c2e9680b4dfc6303e73daf15f1464da71c0bb05f47a8def7` |
| `build/user-login-evidence/final-vms/report.json` | `2dc2a485a8885d3e442aa13a57ef3f62ab958be0b5604e32c93c5d7e2d8b88ed` |
| `build/user-login-evidence/compat-vms/report.json` | `103a1d10c1e95f90e29629c0d793d66fb330114bcde74b1738362af04435d3cd` |
| `build/user-login-evidence/host.log` | `4d15e083dbf6045936dba9f1adca776dc23cd4724ef694a8c5b1d221368ebe38` |
