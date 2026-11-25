# efc3a5ff：XOS Integration Campaign 阶段整合与复验

2026-11-26。起始 `main` 为 `5e49012ab2b359b31999d78083341ede98d5de4f`。
代码与契约收口至 `6c1f0f825f608d4ac641a5da16225ea5276c6d99`，树
`bed06d35604b6af1137f2ff7fceeca0fdad6d9f0`。表中每项以实际受测树为准，
最终主线资格在最后一节登记。

## 主线进展

- 已合入 #159、#155、#158、#149、#169、#150、#162、#165、#167、#151–#154、
  #157、#156 和 #168。#142 原头随 #149 进入祖先，#148 原头保留并说明后关闭。
  [G1 记录](2e973a40_glibc_g1.md) · [历史交接](8edae993_glibc_g2_g3_takeover_audit.md)
- #156 实际合并 `f4ba8a3e342442d34c8d009e1c0ac744843270ca`。活跃线程普通
  exit 使用 sys51 有界清理，保留 fork 预备/提交门禁修正。主动阻塞 stdout 的
  控制用例仍要求超时状态 127。[退出记录](8bfdcae1_glibc_active_process_exit.md)
- #168 实际合并 `96934167bd183d099d4fd268a7db623b99559e9d`。共享 FD lease/RPC
  和 IPC 生命周期合流。#161 的原头 `dcb7d95735cff2699c089519235a337e857085d2`
  是该实际合并提交的祖先，已核实后按承接关闭。
  [共享依赖记录](c28d41a6_glibc_shared_dependencies.md) · [wait-any 契约](../contracts/process_wait.md)
- #160（`c018bc054093`）保留原目录流、定位 I/O 及线程 SDK 清单修正，
  #163（`e828f5ae1544`）保留独立 terminal/termios 阶段。#164（`74cf265a55b9`）
  提供双 SDK 候选准入，#166（`cd5e33924d3a`）完成 D0 契约。
- #170（`fdaed0b2f130`）修正 P2 维护恢复夹具，#171（`bb38faaa7be2`）修正 BIOS
  光盘读取时限，#172（`6c1f0f825f60`）修正 dash PATH 查找 XOS ELF 及受支持脚本。
  #172 的累计候选 P1 客体验收 11/11，覆盖两种 Shell、升级卸载、重启及资源恢复。
  [定位 I/O](d742abe1_glibc_positioned_directory.md) · [终端](../contracts/glibc_terminal_v1.md) · [D0](../contracts/dynamic_linking_d0.md)

## 阶段证据

| 范围 | 绑定输入与结果 |
| --- | --- |
| #151–#154 基础链 | 实际合并树依次为 `8ee5e3e6`、`168bbfd2`、`c1e46645`、`5079d325`。Linux arm64 宿主的 x86_64 BIOS QEMU 11.1.3 下，xsh 为 9、12、10、31 次，dash 为 9、12、9、30 次。含 Sys35、明确的文件服务故障镜像、glibc 上游签名与静态 SDK。 |
| 共享候选 `68226271` | 绑定同一 SDK 与镜像的完整复跑中，xsh 73 次、dash 39 次、终端 6 次及终端负向控制通过。wait-any 27 次/10 组、IPC exec 3 次和 N2 13 项另有同树记录。首次 status 95 出现在文件内容确认后的 `close`/`unlink` 清理，原报告保留。随后独立退出 39 次、辅助诊断 24 次及完整复跑未复现。 |
| #160 SDK 清单复验 | 在独立 PR 树 `af44f16b8634db5ed573cb88b347897345270b5a` 重建普通系统及 C-only 线程 newlib SDK。两份清单均声明文件操作 20–31，目录身份标志 `4096`、记录头 13 字节、操作 30/31 及共享偏移保留字段一致。线程 SDK 校验 162 个输入、1302 个产物，ABI 和 AArch64 编译检查通过。客体资格沿用 `not_run`。 |
| 网络 #162/#165/#167 | 实际 #167 系统 `6fa87677f1b43c0d` 的 QEMU 11.1.2 传输 15/15、生命周期 13/13、VirtIO 3/3。DNS 宿主普通与 ASan/UBSan 各 43/43。生产 DNS/DHCP 保持关闭。 |
| Aurora 与双 SDK | 候选树 `7d1d2d2d` 上的 Aurora 有本地 38/38 和受控 HTTP 9/9，绑定实构建 Qt Widgets 和线程 newlib SDK。同树独立 glibc C/C++ 通过 xsh/dash 各 12 次，覆盖构造析构、iostream、线程和并发展开。配置维持候选身份。 |
| xypm | #159 离线 P3 对照和拒绝路径客体 20/20，覆盖精确锁、安装、升级、移除、事务和重启后回读。P2 维护恢复的追加修复在候选组合中单列复验。 |

[网络复验](69b0e274_network_guest_readiness_and_window.md) · [P3 客体](7c2de8a4_xypm_p3_preview_guest.md) · [SDK 过渡](9df72e1b_xypm_dual_sdk_profiles.md)

#154 阶段的系统 manifest SHA-256 为
`d5fd498d8c4f8ddd6f75b85e4e3fea792286c8c27e4296ce627a50e3ee063cdc`，glibc SDK 为
`5c9bea6024bcb9a5e4d7458e5c64bd955c24dc5d0a133e9be049790b21894e59`。
#160 清单复验构建为 `bed8ba1417409937`，普通 SDK 清单 SHA-256 为
`1e802bc8a6cc67f6c2d47cc8fda1db6eef80bf3cbeded009979d9015ab35707f`，线程 SDK 清单为
`4856025b7b4e637754ccaea40080e6885811d1ec584fe3d2285dbb959762c418`，对照报告为
`072182b4952059bd677a499427fbc515a28518fa9abe677c51b7b56a93cf96c4`。该回归校验清单
和编译，应用与客体的文件能力仍由运行时及其单独验收提供。完整阶段和
原始失败证据在各自独立构建目录，整合报告由 `build/integration-campaign/acceptance-report/`
汇总并按实际输入绑定。各阶段只承接对应源码与配置的资格。

## 最终主线验收待做

从实际最终提交使用新输出目录重建系统、newlib SDK 和经源认证的 glibc SDK。记录实际
工具、固件与配置，校验普通与专用故障 ISO、各 SDK、ELF、源码和报告摘要。正式入口为
`scripts/build.py`、`scripts/build_glibc_sdk.py` 与 `make smoke`，并分别执行 ABI、glibc、
IPC、网络、Aurora、包管理、双 shell 和资源回收验收。已观察的前内核 ISO 读取失败与
临时文件同字节复验保留原各自结论，候选 BIOS 时限修复需匹配最终镜像回归。

最终主线构建 ID、各产物摘要、整体验收和发行准备裁决待填。历史冻结报告、newlib 默认
SDK、N4 生产禁用与 D0 契约的状态按各自记录追踪。
