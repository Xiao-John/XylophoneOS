# dcbbd42a · Mobius、ClarkE 与外部 Qt Quick 同盘复验

从 `a9adedbb` 主线（含 #259、#262）和此验收提交 `dcbbd42a` 构建普通
系统 `b695ba740f69aa59`。使用 QEMU 11.1.2，普通 xsh 和实际 Display、
Interactium 服务。两个 XPK 在同一个经过 glibc SDK 绑定的 512 MiB FAT32
工作盘上安装，之后在四次清洁启动中复用该盘及卸载后的派生盘。
[客体回执](../reports/desktop_products_combined_20261126/report.json) ·
[证据清单](../reports/desktop_products_combined_20261126/manifest.json)

- `xos.mobius` 的 `mobius.elf`、`mobius-session.elf` 分别启动。键盘输入
  切换到不同主题并取得探测画面，每次退出后均回到显示服务基线。该次会话
  启动耗时 183.572 秒，仍需单独关注启动性能。
- `xos.clarke` 读取已安装的 `/web/start.html` 和 `theme.css`，产生浏览器
  画面并从键盘退出。卸载 `xos.mobius` 后，ClarkE 安装清单与用户文件保持，
  ClarkE 再启动产生相同的画面摘要。此处使用 ClarkE 本地导航，受控网络的
  回执见 [安装包 HTTPS](7e05f732_clarke_installed_https.md)。
- 独立构建的 Qt Quick 样例从同一工作盘启动，其 260×160 窗口出现预期背景和
  文本像素，定时退出，输入线程成功回收。相同 ELF 此前以外部项目构建并独立
  验收。 [样例构建记录](b9673c26_qt_e19_external_quick_application_builder.md)

每轮都在程序退出、显示服务退出两个时点复核空闲页、任务和完成记录，回到
相应基线。源工作盘的摘要保持不变。此组覆盖同盘安装、独立启动与卸载，
并行运行多个顶层窗口、硬件加速和生产网络仍待各专项验收。

## 复验命令

`SYSTEM` 指普通系统产物目录，样例 ELF 由 Qt Quick 外部构建入口输出为
`build/bin/quick_app.elf`，其 `receipt.json` 由同一次构建生成。两个 XPK
须使用同一 glibc profile。

```sh
python3 tests/desktop_products_combined_guest.py \
  --system "$SYSTEM" --sdk "$SDK" --profile "$PROFILE" \
  --mobius "$MOBIUS_XPK" --clarke "$CLARKE_XPK" \
  --quick "$QUICK_ELF" --quick-receipt "$QUICK_RECEIPT" --output "$OUTPUT"
```
