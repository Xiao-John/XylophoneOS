# d6ead81f · 统一 glibc 候选的代表应用与 profile 矩阵

在独立工作树从 `aece9965` 构建普通和安装镜像，显式选择统一静态 C/C++ profile `xos-x86_64-glibc-unified-cxx-v1`，SDK manifest `b21c8b63…`，profile `97385873…`。该批以可重复安装的 stock 路径为验收单元，保留此前各 profile 的独立盘。SDK 的默认选择和退役条件遵循原迁移计划。
[统一 SDK PR #313](https://github.com/Xiao-John/XylophoneOS/pull/313) · [默认迁移计划](../plans/glibc_port_scout.md#从加固期走向默认切换的门)

## 来源与验收单元

| 应用 | 本批边界 |
| --- | --- |
| dash 0.5.13.5 | 用同一 SDK 重新编译并装入 XOSBND1。首个外部 ELF、实际命令替换及冷启动后的命令搜索由真实 Xsh 和 dash 验证。 |
| xypm 0.4.0 与 13 个日用工具 | 从锁定 sbase 及当前 native xypm 重建。空盘自动安装、重启读回、真实工具输出、原生卸载、保留用户文件及提交清理共同组成这一门。 |
| GNU Make 4.4.1 | 以锁定源归档、分离签名和指定 GNU keyring 重建。随同一工作盘运行 GNU Make 与真实 shell 配方。工件以 ELF 导入，独立包生命周期另验。 |
| 外部 C 与 C++ | 用可搬移 SDK 构建并打包既有样例。C 与 C++ XPK 绑定同一个 SDK，检查 stdio、线程、C++ 异常、FAT 读回和两个实际启动入口。 |
| CPython、ncursesw/Vim | 各自已有旧 profile 的构建或运行证据，进入统一 profile 的独立重建和真实运行尚待验收。 [CPython](bbf38ffb_cpython_stock_glibc_guest.md) · [Vim](../plans/terminal_editor.md) |
| Qt Quick、Mobius、ClarkE | 各自的既有 profile 和相应许可证材料保留。ClarkE 原生栈查询随统一 SDK 走过客体探针，浏览器与桌面套件仍需从统一 SDK 的输入重建和运行。 [Qt Quick](7d5f052e_qt_quick_verified_release_sources.md) · [ClarkE 栈查询](207c6644_clarke_native_wtf_thread_and_stack_slice.md) |

## 实际安装结果

镜像 `b210965441f899cc` 的 XOSBND1 安装在 168.411 秒到达可用 Xsh，五项检查通过。另一次安装并冷启普通 ISO 后，从盘执行 `basename`、`cat`、`cp`、`dirname`、`head`、`ls`、`mkdir`、`mv`、`rm`、`rmdir`、`tail`、`tee` 和 `wc`。原生 xypm 核对 26 个受管文件并卸载，全部 33 份输出与预期逐字节匹配，非受管用户文件保留。该镜像的 10 项许可材料通过，开放项为零。

组合测试先离线安装两个外部 C/C++ XPK，再用同一工作盘实际启动安装 ISO 和普通 ISO。两次都通过签名源码构建的 GNU Make、Make 的真实 shell 配方、C/C++ 程序、日用工具和 dash 命令替换。每次停机核对三个包与 50 个受管文件，最终读回 dash、GNU Make 和两份状态文件。进程和内存回收符合两次各自的基线。该候选的全量 `make smoke` 字段保留 `not_run`，上述是安装专项和真实应用矩阵的独立资格。

## 两代 glibc 与冻结 newlib

三张 FAT 原始盘分别按统一、冻结 stock、冻结 ClarkE LLInt profile 离线创建，之后只在各自的盘副本运行用同 profile 构建的 native xypm。统一和旧 stock 均使用真实日用 XPK，ClarkE 使用由其冻结 SDK 打包的外部 C 控制样例。每种角色都原生拒绝另外两类 XPK，宿主包检查给出同方向拒绝。六次拒绝后启动镜像的恢复程序确认无事务。每角色的拒绝盘与同配置仅启动盘在相同冷启动次数下全盘摘要相等。三个原 profile 的数据库、索引、已安装文件和用户数据通过客体及停机读回。首轮将一次冷启和两次冷启直接比较，得到原始盘差异。更正后分别保存启动对照、拒绝盘和两者冷启副本，按匹配的启动次数比较。

原 1024 newlib 的发行镜像和 #296 已资格工作盘在保留的只读输入上复核。用独立盘副本冷启真正历史镜像并运行旧应用，应用读回原数据后追加测试标记。原盘未写入，旧包仍由原 profile 验证，统一日用 XPK 与旧应用 XPK 在互换 profile 的宿主检查中均拒绝。
[原发行回退](4ffa226d_glibc_stock_fork_frozen_rollback.md)

## 复现

用隔离的 Linux arm64 环境、QEMU 11.1.3、锁定交叉工具和独立输出目录。`UNIFIED_KIT` 是已资格的可搬移静态候选，`SBASE` 指向锁定的源目录。用统一 kit 重新构建 `selection.kit_c`、`selection.kit_cpp` 的原样例及签名 GNU Make。沿用已有组合阶段的命令与源材料。
[外部应用与 GNU Make 命令](cc71c241_glibc_stock_apps.md)

```sh
candidate=build/candidates/unified-static-matrix
python3 scripts/build_candidate.py --output "$candidate" --glibc-app-kit "$UNIFIED_KIT" \
  --glibc-daily-source "$SBASE" --installer-guest
python3 tests/glibc_selected_app_matrix_guest.py --candidate "$candidate" --sdk-kit "$UNIFIED_KIT" \
  --c-xpk build/matrix/apps/external-c.xpk --cxx-xpk build/matrix/apps/external-cpp.xpk \
  --make-manifest build/matrix/apps/gnu-make/manifest.json --require-command-substitution \
  --output build/matrix/cold-apps
python3 tests/glibc_default_profile_matrix_guest.py --system "$candidate/system" \
  --inputs build/matrix/profile-inputs.json --output build/matrix/profile-guest-new
```

`profile-inputs.json` 以 `unified`、`stock`、`browser` 三个键保存 `kit`、`package`、`xypm_receipt`。系统和套件验证使用各自的真实 manifest。统一套件可传入安装器产出的 `stock/xypm.json`，其余两份 xypm 用 `scripts/build_xypm.py` 和各原 kit 构建。旧 stock 包取旧候选的 `stock/daily.xpk`。ClarkE 控制样例使用旧 kit 的 `xos-app init --language c --id selection.browser_profile_control`、`build`、`check`、`pack`。各阶段的受控盘与日志均位于独立输出目录。

PR 基线 `1adaa908` 已包含统一 SDK、Qt Quick 材料、普通镜像的组合证据与 ClarkE 软件绘制。对比实际构建源码 `aece9965`，内核、用户态、配置、glibc、sbase、dash、GNU Make、构建脚本及本次使用的回归入口未变。客体结果继续绑定 `aece9965` 的实际镜像。默认入口、完整存量产品重建和 newlib 退役由后续组合资格决定。
[构建绑定和客体证据](../reports/glibc_unified_default_matrix_20261127/manifest.json)
