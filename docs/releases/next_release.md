# 下一次 XOS release：准备清单

2026-10-26。状态：**0.0.1-1026 候选已构建并跑完 release smoke；待用户确认后提交源码/发布**。
本页只做 release 准备；不修改已发布的 0.0.1-1024 资产。

## 必须先解决的阻塞项

1. **ISO扩容已完成（0047）**
   kernel文件8 MiB/内存16 MiB、payload32 MiB；真实5.6 MiB kernel与2.1 MiB
   载荷通过容量10项，正常启动兼容4项通过。候选在build/iso_capacity/normal，
   build4c79f3a789dcff61，安装ISO SHA256
   4e7b5351cbd8a4988423334ed50e52940b4c414b56eb1453b500bb36d9f9df76。
   此目录是正常候选；父目录的probe kernel/trailer dash仅用于验收，不进发行。
2. **统一release构建与资格**
   0047/0048已共用正常候选，P2-1 8项和许可材料检查通过。仍需按发行冻结
   SDK、dash/CPython/工具链并取得对应回执，旧911184/f25009回执不能自动改绑。
   不自动改写共享build或替换已发布0.0.1附件。
3. **决定是否回滚工作盘预装 dash**
   新 install ISO 会自动安装 dash；旧 `make disk`/发行盘预装是否删除要在
   release 前统一决定。当前代码仍保留 `--with-dash` 和
   `scripts/install_dash.py` 作为兼容/应急，不是最终 release 形态。
4. **release 工具**
   `VERSION` 已为 `0.0.1-1026`，`package_release.py` 已按版本目录工作；仍需
   在源码提交后生成 source materials 并把提交哈希写入发行回执。

## 当前候选回执

- build `7a4668477d7323de`；release smoke 11/11，资源 `[130272,2,0]`。
- install ISO SHA256 `db2f607781a7818a5238eaecb86c13d63f449383cf9a8e32be4590e83b594f12`。
- images/SDK tar 已生成；许可审计 7 份材料通过，成员级审计仍开放。
- 候选目录 `build/releases/0.0.1-1026`；源码提交后重新生成 source materials。

## 验收 gate

发布前至少重跑并在 release manifest 记录：

- `make build`；必要时 `make threading`/SDK 构建（按冻结 profile）。
- 启动/shell/files：`tests/shell_smoke.py`、dash B2 报告。
- xypm：`build/package_p1/xypm_acceptance/guest_report.json` 10/10，宿主
  P0/P1 报告；使用私有测试盘。
- CPython T3-PY：`tests/cpython_t3_py_smoke.py`，5/5 和资源恢复。
- ISO：A2、A3/A4 两项客体测试，使用新 build 和新 ISO。
- 许可/SDK 材料：`make license-audit`，GNU/newlib 材料检查；未完成项保留。

旧压力、SMP、T3-QT、P2/P3 未过不能写进 release “全部通过”。

## 打包与压缩材料

- 生成新的 `xylophoneos_revival_<version>_images.tar.gz` 和 SDK；不要覆盖
  旧版本附件。
- 同步 `system_manifest.json`、`release_manifest.json`、安装 ISO 和
  `MANIFEST.TXT` 的 SHA256。
- 源码/许可材料按 `docs/releases/source_materials.md` 重新生成；压缩包内
  必须含版本化 manifest，不能用旧 0.0.1 的 168 MiB 源码包冒充新版本。
- 旧 0.0.1 的顶层重复源码压缩包已清理，canonical 在
  `build/releases/0.0.1-1024/sources/`；GitHub 远端附件不受影响。
- `src/ports/dash/upstream/dash-0.5.13.5.tar.gz` 是离线构建输入，保留。

## 公开说明与工程材料

公开release notes遵从用户指定的纪念发行风格：简洁，只介绍已有功能。
build ID、产物哈希、SDK/profile、通过/失败/未运行及已知限制保存在manifest、
验收报告与工程文档；完整证据不靠公开发布文案承担，不把未验证能力写成已有。
