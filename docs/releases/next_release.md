# 下一次 XOS release：准备清单

2026-10-25。状态：**准备中，未冻结版本号，未重新打包**。本页只做 release
准备；不修改已发布的 0.0.1-1024 资产。

## 必须先解决的阻塞项

1. **ISO 扩容（不由本清理组负责）**
   当前 `xos-install-dash.iso` 已能把 `KERNEL.BIN` 从 ISO 读入并安装 dash，
   但容量仍受：
   - kernel 构建上限 `config/x86_64_bios.json` 的 512 KiB；
   - loader 页表只映射前 4 MiB；
   - payload 上限 1 MiB。
   负责 ISO 的组需要解除这些限制，并用大于 640 KiB 的真实 kernel/ISO gate
   验证，而不是只验证 344 KiB kernel。完成前，release notes 不能宣称
   “ISO 容量已突破”。
2. **用当前源码重建 install ISO**
   现有 A3/A4 报告绑定 build `26eb667dd8318997`；最近完整 gate 是
   `911184be3f3c99f6`，当前源码重建为 `f25009cdbb27c857`。需要
   `make build dash install-iso` 后重跑
   `tests/iso_file_kernel_smoke.py`、`tests/iso_dash_install.py`，更新哈希。
3. **决定是否回滚工作盘预装 dash**
   新 install ISO 会自动安装 dash；旧 `make disk`/发行盘预装是否删除要在
   release 前统一决定。当前代码仍保留 `--with-dash` 和
   `scripts/install_dash.py` 作为兼容/应急，不是最终 release 形态。
4. **更新 release 工具**
   `VERSION` 和 `scripts/package_release.py` 仍固定为 `0.0.1-1024`；新
   release 需要更新版本、system manifest、install ISO 入包和 release notes，
   不能直接复用旧目录。

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

## Release notes 最低内容

- 版本/日期、build ID、kernel/ISO/SDK 哈希。
- 已通过 gate 与未运行项分开写。
- ISO 扩容状态；若未完成，明确“install ISO 可用，容量仍受限”。
- xypm/CPython/dash 的能力边界；不给未实现 POSIX/P2/P3 承诺。
