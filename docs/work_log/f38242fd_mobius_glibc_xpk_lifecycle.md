# f38242fd — Mobius glibc XPK lifecycle

2026-11-26 · `xos.mobius` · 私有开发候选。使用前一阶段已验的 [Mobius glibc Widgets
桌面与会话 ELF](8f0020c4_mobius_glibc_widgets_guest.md) 打包。正式客体路径仍为
`/usr/bin/mobius.elf` 与 `/usr/bin/mobius-session.elf`。

## 构建与回执

`package_desktop_products.py` 对 glibc 候选复用普通 XPK 应用的 SDK/profile 核验与
许可材料选取。`--sdk` 使用 glibc SDK 构建根。两个 ELF 逐个核对其构建回执、完整
SDK 树与 manifest、目标工具摘要、原始构建输入及静态 ELF。包内回执绑定两份原始
回执的摘要和实际 profile。包内 SDK 材料来自同一依赖集，包含 glibc、GCC C++
运行库和 XOS 端点支持的许可文件。Qt 材料沿用现有产品配方，正式分发与静态重链接
资格需另行核对。

```sh
python3 scripts/package_desktop_products.py mobius "$MOBIUS_BUILD/mobius.elf" \
  --session "$MOBIUS_BUILD/mobius_session.elf" --sdk "$GLIBC_SDK_BUILD" \
  --profile "$GLIBC_PROFILE" --output "$MOBIUS_XPK"
python3 tests/mobius_glibc_xpk_guest.py --system "$D87_SYSTEM" --target "$MOBIUS_BUILD" \
  --package "$MOBIUS_XPK" --legacy "$LEGACY_DESKTOP" --legacy-receipt "$LEGACY_RECEIPT" \
  --sdk-build "$GLIBC_SDK_BUILD" --profile "$GLIBC_PROFILE" --output "$MOBIUS_XPK_GUEST"
```

既有 newlib Mobius 输入重打包的 SHA-256 与冻结候选逐字相同，均为
`eb7dec9c8fa8ff1f920d2b50f4cf5d35c8f59f04a8e324516b4e18d13e964baf`。

## 旧盘与客体

独立 FAT32 源盘放入真实的旧版 newlib `/bin/desktop.elf` 和一个未纳管的用户外观文件。
宿主执行离线安装和卸载候选事务。安装后用 d87 默认组合系统 `d82908b725ffd19a` 启动
产品的桌面和会话入口。卸载后再次启动同一系统，经保留下来的旧路径运行原有桌面。
每次启动检查真实 PS/2 控制、VGA scanout、正常退出与资源计数。

- 安装核对 29 个纳管文件及包内回执。直接桌面入口在 25.333 s 就绪，会话入口在
  191.367 s 就绪。桌面内采样分别为 2,600 ms 和 2,080 ms。
- 卸载后的纳管文件计数为 0。旧 `/bin/desktop.elf` 和用户外观文件保持原摘要，旧版
  桌面在 21.272 s 就绪。三次启动的 Midnight 与 Daybreak 分别取得相同的 VGA 像素。
- 三次桌面正常退出后均恢复到 `[121635, 5, 3]`。两轮图形服务退出后均恢复到
  `[129711, 3, 1]`。原始旧盘始终保持原摘要。
- 冻结 newlib profile 拒绝 glibc XPK。单独试验向副本回执写入不匹配的 G++ 摘要，
  打包被拒绝。在副本中预放用户所有的 `/usr/bin/mobius.elf`，安装被拒绝且保留原文件。

| 工件 | SHA-256 |
| --- | --- |
| glibc `xos.mobius` XPK，两次构建一致 | `cb8522a405f9902e26d82b453f0b1f25592710245cad48cb651c3fdb40bd8a45` |
| glibc SDK manifest | `7eee04884a96ced6de12d20794af6809f544e3f15bc4e409b4197e58b1583d7a` |
| d87 ISO | `64230b48317bb327fcac03651982381b98912da10a3256e98b73d7d3091fa1f5` |
| 保留的 newlib 桌面 ELF | `c5cc0f7269a8def49ff2ec15a633833869a65d8adca218aaf68d2861d9673592` |
| 生命周期回执 | `66f7ac5b6d4a85234f5957b76971a6c491e0371ad32a9525dcfdc72381b342fe` |
| 安装后串口 | `fd44468d4742317a344a0d0756e24069f97e3a60b2e4a557d43219a4767864cf` |
| 卸载后串口 | `9a8f4c9b59773dea6d1f4f9b413c7d0041fd8b48047edb5bd1d6a16a2522f1c2` |

压缩 XPK 原件、回执、串口和去重 scanout 保存于本地 `build/qt_glibc/mobius_e17/xpk/`。
此次验收覆盖宿主离线安装、卸载和客体启动，后续组合系统、glibc ClarkE、包升级、客体内
安装事务与正式分发各自待验。

## 会话文件装载计量

独立诊断会话通过链接器 `--wrap=xos_file_session_exchange` 计时原有 libc 实现，启动
同一桌面 ELF。共计 18,077 次文件服务交换，其中 12,047 次读取、6,026 次 seek 及
4 次其他交换。每次计量均得到非零经过时间，客体单调时钟累计 184.760 s。该次宿主
记录的会话就绪耗时为 192.836 s，应用内采样为 2,540 ms。诊断会话同样通过 VGA、输入
和回收检查。XPK 生命周期用原先的应用和会话 ELF 单独验证。

诊断会话 ELF 摘要为 `7782c5eef7e88c39af0f554dacee6f6d539f3e01b4f16ab3bb9282b9dcab0f9e`，
回执为 `1068f7f3677f8b5661c08fc61066723f421a173987d172f282e4d42d7fbbe65d`，
串口日志为 `ab2e98fd6a0700bd9342ee442d60aa2fbc119da8e25079c9fda15e616b5cb4f6`。
构建配方、包装器与原始回执保存在证据目录的 `ipc_probe/` 下。
