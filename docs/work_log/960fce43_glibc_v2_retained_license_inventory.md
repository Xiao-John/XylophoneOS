# 960fce43 · 保留发行候选的许可与重链接清单

核对当前保留的十件候选资产及统一校验表，发行清单 SHA-256 为
`fd95e47c8f99205f1ff1ec6ac77537e00b9f7a46d77046d787ae4d03c361e588`。
从实际安装 ISO 解析 XOSBND1，按发行摘要复核已解包的原工作盘、三份 XPK、
GNU Seed 源归档和补充源归档。工作盘端逐个导出清单中的可执行文件并核对 ELF、
符号和摘要。30 个普通系统的 `.image.elf` 同时按系统清单核对。29 个可读取符号
表的文件均无 glibc 启动标记，另一个是故意破坏 ELF 魔数的验收夹具。
[逐程序摘要与实际许可文件](../reports/glibc_v2_retained_license_inventory_20261127/manifest.json)

| 交付组 | 实际材料和对应关系 | 待验 |
| --- | --- | --- |
| GNU Seed 的 GCC、Binutils 和前端 | 12 个路径绑定冻结 donor 的源码、构建回执和许可。两条汇编器路径同字节。12 个 ELF 均含 newlib 的 `_impure_ptr`；同发的目标 sysroot 是 glibc v2。嵌套旧 GNU 源包的 GCC 16.2.0 原档已流式核对与 v2 SDK 源锁一致。 | 各自条款与替换材料按旧 GNU Seed 对应记录及实际成员核对。 |
| GNU Make `gmake` | 当前盘上实际静态 glibc ELF。GNU 源归档包含 4.4.1 原件、签名、公钥、六项配方输入及 COPYING。当前候选的接收验签回执精确绑定该源归档和签名者。 | GNU Make 的接收方可替换 libc 重链接。 |
| 安装器 Dash、xypm | 实测安装容器有两个 glibc ELF 和 daily XPK。补充归档包含 Dash 的源码、补丁、构建输入与许可。xypm 归档绑定当前发行清单、SDK 和实际 ELF 的摘要。 | Dash 的发布对象与替换验收。xypm 的既有替换客体回执适用其实际对象、SDK 与历史客体绑定。 |
| daily XPK | 13 个静态 glibc ELF、10 项许可；对应归档含锁定 sbase、XOS 源和实际构建回执。 | 每个日用程序的发布对象与替换验收。 |
| CPython/zlib XPK | 一个静态 glibc 解释器，唯一额外静态扩展为 zlib；11 项包许可和 558 个标准库成员。对应归档中 Python 与 zlib 原件、补丁、相关构建回执均绑定实际包。Python 上游签名已有同一源档摘要的独立证据。 | 该解释器的发布对象与替换验收。 |
| IDNA XPK | 纯 Python，实际包含许可证，补充归档含匹配的原始 wheel。 | 通常随包核对本组源码与许可。此组没有需要替换 libc 的 ELF。 |

当前受清单约束的 17 个 glibc 程序路径中，只有 xypm 带经回执绑定的独立
重链接归档。Dash、13 个日用命令、CPython 和 GNU Make 共 16 个路径仍须交付
对应对象、准确链接配方及所需的成员许可，并用接收方实际替换验收闭合发布门。
CPython 整包复现和 stock 客体现有回执仍按各自适用的输入和客体使用。
[xypm 独立重链](7209d6e4_glibc_v2_release_xypm_relink.md) ·
[新 CPython 客体](458f4933_glibc_v2_cpython_stock_guest.md)

应用 SDK 携带 glibc 2.44 的锁、签名、公钥、补丁、构建辅助与许可。
原始 glibc 源档 `37f600f2bef3c5e8300147059568b2a2e40a7ad6ccc65ce942556d49429cc667`
在本地找到，并与随 SDK 的已验签记录一致。它未出现在现行 SDK、组件源、
GNU Seed 对应源或 xypm 重链归档内。离线接收材料还需将该共用源档与明确的
重建入口绑定到最终发布资产。现有 GNU Seed 源包内的 GCC 16.2.0 原档可复用。

## 复核方法

在源码树中将 `INVENTORY_FILES` 指向下方回执目录。提供保留的发行资产、已经脱离
生产目录解包的发行原件、同候选的 GNU Make 上游验签回执和普通系统实物，
以及 Python 已验签回执。运行使用现成 Darwin arm64 FAT 后端和
`x86_64-elf-nm`。将编译器阻断脚本置于 `PATH` 最前，与本次复验一样拒绝
隐式编译。盘读取使用只读模式，每次导出一个 ELF，校验后即删除。
`--glibc-source` 可选，用于同时核对已经取得的原始 glibc 源档。

```sh
mkdir -p "$SCRATCH/no-build"
for tool in clang++ c++ g++ gcc make; do
  printf '#!/bin/sh\nexit 99\n' > "$SCRATCH/no-build/$tool"
  chmod +x "$SCRATCH/no-build/$tool"
done
PATH="$SCRATCH/no-build:$PATH" PYTHONPATH="$PWD/scripts:$PWD/tests" \
  python3 -B "$INVENTORY_FILES/audit.py" \
  --retained "$RETAINED_ASSETS" --reopened "$REOPENED_RELEASE" \
  --proof-dir "$CANDIDATE_PROOF" --system "$CANDIDATE_SYSTEM" \
  --python-signature-receipt "$PYTHON_SIGNATURE_RECEIPT" \
  --scratch "$SCRATCH" --glibc-source "$GLIBC_SOURCE" > "$SCRATCH/inventory.json"
```

此次只读复核没有重编、客体启动或发行上传。保留的工程清单和签名材料用来追踪
实际资产及仍需验收的分发材料。
[清单与复核入口](../reports/glibc_v2_retained_license_inventory_20261127/manifest.json)
