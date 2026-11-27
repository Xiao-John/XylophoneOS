# 960fce43 · glibc v2 发行候选组合复验

在主线 `960fce4347f193f13f5214caee153a03891ab100` 的干净树上用已核对的
v2 SDK 与锁定 sbase 重建普通及安装 ISO，得到系统 `1f593b6ca9cd7904`。
核对构建清单登记的 301 项实际工件。发行沿用冻结的 GCC/G++ 和 Binutils 供体，
更新 v2 sysroot，并将日用工具、此次重建且固定归档的 CPython/zlib 和 IDNA 装入
同一工作盘。发行清单与原始工作盘 SHA-256 分别是
`fd95e47c8f99205f1ff1ec6ac77537e00b9f7a46d77046d787ae4d03c361e588` 与
`d3c51769258094448a30b57d6028456405888b0501ceebad4ad178234c26df45`。

## 实测

| 范围 | 结果 |
| --- | --- |
| 普通及安装介质 | 锁定的 QEMU 11.1.2 通过 79 项普通客体和 10 项登记材料检查。ABI 与 78 个已分配 syscall 文档一致。QEMU 11.1.3 实际安装器通过五项，普通启动运行 13 个日用工具并核对 33 个输出。 |
| 发行盘包生命周期 | QEMU 11.1.2 通过四项。验证装盘及幂等重跑、普通介质冷启、错 profile 包无事务拒绝、卸载 daily 和 IDNA 后保留 CPython 与用户文件。随后逐项核对盘上的 1,376 份 GNU Seed 文件。 |
| 发行盘原生工具 | 同一原始盘的另一份副本通过 20 项。客体直接用 GCC/G++ 编译和执行，分别从 Xshell 和 Dash 驱动 GNU Make。C/C++ 链接图使用 v2 sysroot。未定义符号被拒且未留下 ELF，冷启后 C/C++ 产物和 Python 发行脚本再次通过。 |
| 接收方资产 | 四份原归档、两个原清单和四份补充资产共十项逐一核对。接收方从归档重开，拒绝缺项、重复、字节不同和多余成员，断网 Linux 核对实际 GNU Make 签名。 |
| 接收方 C/C++ 工具包 | 仅挂载从归档重开的 SDK 目录。断网 Linux 从仓库外调用包内 `xos-app` 构建、检查、打包 C 与 C++，拒绝覆盖 profile。两份接收方样例的客体运行未执行。 |
| 源码和重链接 | 核对组件源码归档中的 135 项，独立从暂存的重链接归档得到与实际发行 xypm 相同的 ELF。 |
| 同盘升级恢复 | IDNA 测试修订在提交前的同步检查点 123 中断。内置恢复器逐字节恢复原数据库、索引和用户数据，随后用发行 xypm 重试成功。冷启验证 CPython、gzip 和 IDNA，以及 58 个受管文件。原发行盘摘要保持一致。物理断电和扇区撕裂未运行。 |
| 冻结回退 | 同一 v2 普通 ISO、绑定包和隔离工作盘通过 v2 → 原版 0.0.1-1024 newlib → v2 三次冷启，另有独立输入及原始串口。此项复用既有 v2 应用盘。 [回退复验](960fce43_glibc_v2_frozen_newlib_roundtrip.md) |

最初 Linux 容器在 Dash 的 GNU Make 阶段被内存组终止。保留十份实物后，
从相同归档重开并转到宿主 QEMU 11.1.2 完成两组测试，核对初盘和全部归档摘要。
冻结 GNU 供体的编译器详细输出仍包含历史构建目录。公开串口和客体收据已移除
宿主路径前缀，并保留原件与导出件的各自摘要。
按主线 `79d71b1d` 再核对，构建、脚本、测试、配置和运行时源码没有变化，
本次工件的源码身份仍是 `960fce43`。
[组合结果、接收校验与容器中断回执](../reports/glibc_v2_current_release_20261127/manifest.json)

## 复跑

按[候选组装入口](9f6b0349_glibc_v2_release_inputs.md#复现) 使用精确源码、工具包和
构建输入重新生成。已持有十份资产时，先用 `sha256sum -c CHECKSUMS.sha256` 核对完整
暂存清单，解包 `images.tar.gz`、`application-sdk.tar.gz` 与 `packages.tar.gz`，
在独立目录保留原归档和清单。接收方测试使用由 `release_manifest.json` 中四份归档及
两个原清单组成的内层校验表，十项外层表留存于原资产目录。

```sh
python3 -B tests/glibc_gnu_seed_release_preflight.py --release "$RELEASE" --output "$RECEIVER"
scripts/release_pipeline.sh smoke --glibc-release "$RELEASE" --output "$GUEST" \
  --foreign-package "$V1_IDNA"
"$RELEASE/application-sdk/xos-app" init "$C_PROJECT" --id receiver.c --language c
"$RELEASE/application-sdk/xos-app" build "$C_PROJECT"
"$RELEASE/application-sdk/xos-app" check "$C_PROJECT"
"$RELEASE/application-sdk/xos-app" pack "$C_PROJECT" --output "$C_PACKAGE"
```

C++ 重复最后四条，使用独立目录、包 ID `receiver.cpp` 和 `--language cpp`。
同盘升级使用[发行升级入口](cd9e6300_glibc_v2_upgrade.md#重跑)和本次重开的发行目录。
本次复用已构建的中断用 xypm。与正式 xypm 对照 22 项构建输入，其中 21 项一致，
唯一变化是在同一源文件首行启用 `XYP_TEST_FAULTS`。SDK、profile 和工具记录一致。

默认发行切换仍以最终接收方取得完整静态材料为前提。glibc 2.44 上游源码与
其余静态程序的替换配方需纳入同一套资产。应在分发前清理供体的宿主构建路径。
Qt、Mobius、ClarkE 与动态装载继续按专项验收。
