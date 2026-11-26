# af27a498 · Mobius 和 ClarkE 私有开发包

2026-11-26。复用 xypm 的 SDK 树登记、ELF 校验、确定性 XPK 和离线事务，构建
`xos.mobius` 与 `xos.clarke`。ClarkE 包额外管理本地起始页、阅读与样式示例。
新工作盘无需预置 `/web`，旧工作盘的文件优先。

## 复现

使用现有 Mobius 和 ClarkE 构建器生成真实 ELF 和回执。将实际线程 SDK 树登记到
测试专用 profile，包含 C++ 与线程能力。SDK、Qt 及工具选用同一匹配构建，当前
工作记录使用运行过 Qt 6.8.3 Widgets 的线程 newlib SDK。生成包和测试示例如下。

```sh
python3 scripts/package_desktop_products.py mobius "$MOBIUS_ELF" --session "$SESSION_ELF" \
  --sdk "$TARGET_SDK" --profile "$PROFILE" --output "$MOBIUS_XPK"
python3 scripts/package_desktop_products.py clarke "$CLARKE_ELF" \
  --sdk "$TARGET_SDK" --profile "$PROFILE" --output "$CLARKE_XPK"
python3 scripts/package_desktop_products.py clarke "$CLARKE_ELF" --revision 1 \
  --sdk "$TARGET_SDK" --profile "$PROFILE" --output "$CLARKE_UPDATE_XPK"
python3 tests/desktop_product_packages.py --system "$SYSTEM" --profile "$PROFILE" \
  --dash-receipt "$DASH_RECEIPT" --mobius "$MOBIUS_XPK" --clarke "$CLARKE_XPK" \
  --clarke-update "$CLARKE_UPDATE_XPK" --output build/products/guest
```

QEMU 11.1.2 在专用 FAT32 盘上通过两次安装、一次 ClarkE 升级、xsh 与 dash
启动两应用、两次独立卸载和用户旧文件回读。初次试验的 256 MiB 镜像在宿主准备
阶段被既有 FAT32 工具拒绝，改用工具支持的 512 MiB 后通过。xsh 与 dash 都
实际显示 ClarkE 内置起始页和 CSS。图形服务活动资源为 `121624 / 5 / 3`，
结束后恢复为 `129700 / 3 / 1`。首份成功报告 SHA-256 为
`56e09f4a8591c01eb7f53bc6174dd562d9427facc87ce5838b95cedbe1f1bb40`。
本轮复用现有线程 SDK，glibc Qt 产品迁移、签名仓库和正式发行材料各自待验。
