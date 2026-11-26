# af27a498 · Mobius 和 ClarkE 私有开发包

2026-11-26。复用 xypm 的 SDK 树登记、ELF 校验、确定性 XPK 和离线事务，构建
`xos.mobius` 与 `xos.clarke`。ClarkE 包额外管理本地起始页、阅读与样式示例。
新工作盘无需预置 `/web`，旧工作盘的文件优先。

## 复现

使用 Mobius 构建器的 `--products-only` 和现有 ClarkE 构建器生成真实 ELF 和回执。将实际线程 SDK 树登记到
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

提交 `d129f34b` 后空目录重建得到系统 `caa77bcfffcc327c`，同系统 SDK 重建 dash。
组合复验再次通过六组检查和五次离线事务。报告 SHA-256 为
`799e4782d5bf0930caf5abbfa738dbc55b5aa5775e746f9ad8a56bb921dccc94`，串口为
`056c8fec3abc8fd13b9c9e7f5b3e9b573c3c6d5b75eb56449d1b270f0ea1f2e4`。

## 评审复验

产品 ELF 回执记录完整 SDK 树的摘要，构建前后重算。包装器核对登记的 SDK 树与
构建回执。仅变更试验副本的 SDK 头文件或 `libxos.a`，保持 SDK 清单原字节，
并将变动副本登记到试验 profile，两个变动均被拒绝打包。

从变更提交 `813c9060` 重建系统 `dcc48dddea8b7785` 和同系统 dash。macOS 两次
宿主执行在 FAT 导出时中止。使用 Linux 独立临时工作盘和 QEMU 11.1.3 复验，
输出目录位于源码树外。通过六组检查与五次离线事务，图形退出后资源恢复为
`129714 / 3 / 1`。报告 SHA-256 为
`ea1115e8cbdd64e137ac0063c06bb609b72a6dac2c5e7c28ebb271c5a4602aa1`，串口为
`747da706ab9abdfe81fbfb59169c673c0a8fe1c194f2423d161817a9a0441e06`。
