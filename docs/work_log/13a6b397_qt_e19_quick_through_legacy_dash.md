# 13a6b397 — Qt E19 Quick through legacy Dash

2026-11-26 · XOS `9f7a9a0f` · G07 软件场景通过第二条客体启动路径。
沿用 [首轮 Quick 客体通过的 ISO 和 glibc ELF](c8f43a1f_qt_e19_software_quick_guest_smoke.md)。
Dash 0.5.13.5 使用该系统构建实例的 newlib SDK 和既有 Dash C3 配方，Quick 子进程
继续使用已验 glibc 目标产物。

```sh
python3 scripts/build_dash.py --sdk "$SYSTEM_BUILD/sdk" --receipt "$DASH_RECEIPT"
python3 tests/qt6_quick_guest.py --image "$SYSTEM_BUILD/xos-install.iso" \
  --system-manifest "$SYSTEM_BUILD/manifest.json" --payload "$QUICK_ELF" \
  --dash-manifest "$DASH_RECEIPT" --output build/quick-e19-dash
```

夹具校验系统镜像、Dash ELF 和 Dash 目标 SDK 的摘要绑定，再将 Dash 放入新测试盘
的 `/usr/bin/dash`。xsh `type dash` 解析到此路径，随后执行 `dash -c /bin/quick.elf`。
将 Dash 回执的 SDK 摘要替换为不匹配值后，夹具在创建测试盘和启动客体前返回失败。
客体启动真实 Display 和 Interactium 服务，Quick 子进程运行两个窗口周期。六张
QEMU scanout 确认文字、移动矩形及 `A` 触发的橙色变化。`B` 完成每个场景，两个
输入线程均 join。xsh 确认 Dash 退出 0。应用和图形服务退出后资源计数分别恢复到
`[121638, 5, 3]` 和 `[129714, 3, 1]`。

Dash 路径的两个场景分别呈现 6 帧、5 帧，采样峰值各为 10,555 用户页。最长相邻
`frameSwapped` 间隔分别为 120 ms、110 ms，采样包含 100 ms QML timer 调度。
扩展后的夹具随后重跑直接 xsh 路径，同一 Qt Quick ELF 再次完成场景和资源检查。

| 产物 | SHA-256 |
| --- | --- |
| Dash C3 新建 ELF | `94be9cc12698f6da03be0737e938f0c3d1f42061c3f89f3bcec869fcfc191067` |
| 系统附带的 newlib SDK manifest | `62f4b37f272b9a9f801459a4b4427f8fd79dacb9cf33741ebbdc2df0c90d44ae` |
| Dash C3 构建回执 | `8fc193cdb14305bc774e787c134fe0e69053701cdb3ca03c5b0a0b5473dcf299` |
| 同一 glibc Quick ELF | `441079cfe3c168dbf939f16a5700ce786ce45a6a6bda2fe4587691b2900699df` |
| Dash 路径客体回执 | `81dc1c92cf7189ce2a10bebd3b1f076b33c23d05de3cbe4b52bd4ae16e05206f` |
| Dash 路径串口日志 | `8e81fe1604a84d988f1d270bba28c1ac1c8eed636390ebc75cc49e416ceaa7c5` |
| Dash 路径六张 scanout 压缩包 | `782919dd76e8e754b76f77f86be3c2c23fc726ba34da3f5b7940e99087144c79` |
| xsh 路径回归回执 | `a78cadce5768eadf5a073e55da73f261cbdbfd86d1bd8e3dabf3161275ae5754` |

回执、串口日志与 Dash 路径的六张截图位于 `build/qt_glibc/quick_e19/dash/`。
