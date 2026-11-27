# 960fce43 · 发行安装器 Dash 的独立重链接

本次复验覆盖冻结发行写入 `/usr/bin/dash` 的 Dash 0.5.13.5。安装介质、普通介质和
只读 SDK 均来自发行清单 `fd95e47c…e588`。从实际安装 ISO 提取 `DASH.ELF`，
验证 XOSBND1 容器并读取类型 1 的 Dash ELF。冻结构建的回执与先前独立接收重建的
回执同为 `870eb4af…f6e`。[对应源码重建](b0a92aab_glibc_v2_dash_receiver.md)

配置后的 Makefile 给出最终链接命令。收集器保存按实际顺序使用的 33 个 Dash
和桥接对象、启动及结束对象、链接脚本和四个库档。SDK 输入与冻结回执逐一核验。
接收入口按摘要核验每个文件和 GCC、汇编器、链接器，仅接受已知的静态链接选项。
用原始库档在断网 Linux 接收环境中重链接，ELF 为 3,315,096 字节，与安装容器
里的逐字节相同。[对象、SDK 文件和链接顺序](../reports/glibc_v2_dash_relink_20261127/materials.json)

在接收方复制 `libc.a`，以测试对象替换 `getpid.o`，保留 `__getpid` 和弱别名
`getpid`。比较 1,686 个有序成员及每个成员的摘要，仅该对象改变。接收工具拒绝
摘要错误的替换档。用经核验的测试档重链接后，从同一个安装器创建的稀疏 FAT32
盘冷启动普通 ISO 两次。第一轮运行由安装器写入的 Dash，第二轮运行离线换入同路径
的 Dash。原版 `$$` 输出 10，替换版输出 773355。两轮均完成内建命令、命令替换、
外部 ELF 和退出码 0，运行前后空闲页、任务和完成队列计数一致。离线读取再次核验
两版 ELF 和探针文件的摘要。[宿主对照及客体原始回执](../reports/glibc_v2_dash_relink_20261127/manifest.json)

| 接收输入或产物 | SHA-256 |
| --- | --- |
| 本地归档，8,566,471 字节 | `d33d07b4e25d7cb3e7424ac2c67dcb92a055ad6e225262311ee15d31e35fe5c3` |
| 归档内的 `manifest.json` | `72b8605772deea2bfa83441dfb90d1cfd752f8d0a6bac5ecc099598f0798206d` |
| 安装介质中的 Dash 与原版重链接 ELF | `f30495d9229d1550bc01b6c6cfb199924058e129d845a6a50c3d303f69e1243a` |
| 使用单一测试对象的重链接 ELF | `4482a58be6bf37022813b0ba11b92ee7b0f4eeede9ef0c31cb5fba5ffaf20dfe` |

## 复验

从 [Dash 独立重建](b0a92aab_glibc_v2_dash_receiver.md) 保留相同的
`DASH_WORK` 缓存子目录，其中含 `manifest.json`、`build/src/` 和桥接对象。使用
配置时相同的交叉工具路径。将解包的实际发行根目录设为 `RELEASE`，候选构建的
`system/` 设为 `SYSTEM`，将 `OUT` 设为独立输出目录。

```sh
RELEASE_SHA=fd95e47c8f99205f1ff1ec6ac77537e00b9f7a46d77046d787ae4d03c361e588
DASH_RECEIPT_SHA=870eb4afbe0234291eea3f73824ecc7147a8a1cce0b8f9c90be0a392023adf6e
mkdir -p "$OUT"
make -C "$DASH_WORK/build/src" -n -W main.o V=1 dash > "$OUT/make.log"
xorriso -osirrox on -indev "$RELEASE/images/xos-install-dash.iso" \
  -extract /DASH.ELF "$OUT/installer.bundle"
python3 -B scripts/collect_release_dash_relink.py \
  --release "$RELEASE" --release-sha256 "$RELEASE_SHA" \
  --bundle "$OUT/installer.bundle" --dash-receipt-sha256 "$DASH_RECEIPT_SHA" \
  --work "$DASH_WORK" --make-log "$OUT/make.log" --output "$OUT/materials"
tar -C "$OUT/materials" -czf "$OUT/dash-relink-materials.tar.gz" .
```

在断网 Linux 接收方仅提供归档、已绑定的 `x86_64-elf-*` 和下列测试脚本。
`ARCHIVE_SHA` 为发行方给出的归档摘要，`MATERIALS_SHA` 为发行方给出的归档内清单
摘要。独立打包时重新计算外层归档摘要。

```sh
bash tests/glibc_release_dash_relink_receiver.sh \
  "$ARCHIVE" "$ARCHIVE_SHA" "$MATERIALS_SHA" "$OUT/linked"
```

将两份 ELF 带到普通 QEMU 验收环境，使用原始安装与普通介质。指定新输出目录。
运行器自行创建和删除 512 MiB 稀疏 FAT32 盘。

```sh
REPLACEMENT_SHA=4482a58be6bf37022813b0ba11b92ee7b0f4eeede9ef0c31cb5fba5ffaf20dfe
python3 -B tests/glibc_release_dash_relink.py --release "$RELEASE" \
  --release-sha256 "$RELEASE_SHA" --system "$SYSTEM" \
  --original "$OUT/linked/original.elf" --replacement "$OUT/linked/replacement.elf" \
  --replacement-sha256 "$REPLACEMENT_SHA" --output "$OUT/guest"
```

本次通过这一版候选的 Dash 对象收集、精确重链接和单一库成员替换。证据范围为安装器
写入的一个静态程序及其接收材料。发行还需将 Dash 归档纳入同版补充资产及校验清单，
并与对应源码和同版 glibc 原档一同提供。测试库只用于本次接收复验。
