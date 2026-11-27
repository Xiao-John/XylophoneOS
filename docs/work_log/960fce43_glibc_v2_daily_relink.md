# 960fce43 · 13 个 daily 程序的独立重链接

冻结发行清单 `fd95e47c…e588` 指向 daily XPK `e41cc466…c192`。以该 XPK 的
实物、内部构建回执 `07646635…3747` 和精确的 v2 SDK 为基线。生产构建的
`stock/tools` 留有 13 份程序对象、调试 ELF 和后端回执。原始构建清单
`153f64fc…8cc8` 与 XPK 内调试剥离阶段的输入一致。各后端链接命令仅程序对象和
临时输出路径不同。归档保留 13 个非库对象、共享链接输入、完整顺序、回执和许可材料，
与对应的 sbase/XOS 源码补充包配套。[对应源码复验](9c747f60_glibc_v2_component_sources.md)

断网 Linux 接收方仅使用对象归档、与 SDK 绑定的交叉 GCC、汇编器、链接器和
`objcopy`。13 份调试 ELF 均精确复现，再用同版 `objcopy --strip-debug` 得到
13 份与发行 XPK 一致的 ELF。调试剥离前后的加载段和 XOS stdio 接收标记通过核对。
错填替换库摘要时，接收入口拒绝并保持输出目录未创建。

测试库只替换原归档的 `exit.o`。在保留原 `exit` 行为的前提下，测试封装先向
标准错误输出固定标记。比较 1,686 个有序成员的实际字节，仅这个成员改变。用该测试
档与同一批非库对象重链接，13 份 ELF 的摘要均发生变化。
[宿主回执及逐程序摘要](../reports/glibc_v2_daily_relink_20261127/manifest.json)

在同一个冻结安装 ISO 创建的稀疏 FAT32 测试盘上，离线核对实际安装的 13 个
`/usr/bin` ELF。用冻结普通 ISO 分别冷启动原版和离线换入同路径的替换版。每个
程序的正常输出、全部命令的退出状态和资源回收通过，替换版的每条工具命令恰好输出
一次退出标记，原版无标记。用离线读回核对替换后的 ELF 摘要。
[客体回执及三份原始串口](../reports/glibc_v2_daily_relink_20261127/manifest.json)

| 接收输入或产物 | SHA-256 |
| --- | --- |
| 本地对象归档，8,464,546 字节 | `144dda7ee48f140c631a9788d9540c5227ef01be50c74873ff105f5f13405710` |
| 归档内清单 `manifest.json` | `6ece324f4204ef22db9bb2aad2321b1612504954e83f5b865473671099293ae6` |
| 仅替换 `exit.o` 的测试用运行库 | `09d72b82ef29c7ea865fa9960459df065e5ff30c554a8aae8d881cc69ff7c2ea` |

## 复验

`RELEASE` 指实际冻结归档解出的发行目录，`CANDIDATE` 指生产构建目录，应带
生产用 `stock/tools`、`stock/runtime` 和候选清单。使用独立 `OUT`。

```sh
RELEASE_SHA=fd95e47c8f99205f1ff1ec6ac77537e00b9f7a46d77046d787ae4d03c361e588
mkdir -p "$OUT"
python3 -B scripts/relink_release_daily.py collect \
  --release "$RELEASE" --candidate "$CANDIDATE" --sha256 "$RELEASE_SHA" \
  --output "$OUT/materials"
tar -C "$OUT/materials" -czf "$OUT/daily-relink.tar.gz" .
```

将 `ARCHIVE`、外层归档摘要 `ARCHIVE_SHA`、归档内清单摘要 `MATERIALS_SHA`、
测试脚本及同版交叉工具交给断网 Linux 接收方。独立封装归档时重新计算外层摘要。

```sh
bash tests/glibc_release_daily_relink_receiver.sh \
  "$ARCHIVE" "$ARCHIVE_SHA" "$MATERIALS_SHA" "$OUT/linked"
```

将两组 ELF 和接收回执送入普通 QEMU 验收环境。同一组冻结 ISO 由实际发行目录
提供。验收临时盘在退出时删除。

```sh
REPLACEMENT_SHA=431e0118151212f0b0283b93a572c58d1dfcabb1643933d3719ba2de5535c28d
python3 -B tests/glibc_release_daily_relink.py --release "$RELEASE" \
  --release-sha256 "$RELEASE_SHA" --relink "$OUT/linked" \
  --replacement-sha256 "$REPLACEMENT_SHA" --output "$OUT/guest"
```

本次覆盖 daily XPK 内的全部 13 个静态程序。发布时需将对应归档及摘要列入同版
补充资产，并与 sbase/XOS 源码及对应 glibc 原档一同提供。测试用库和离线换入
只用于一次性验收盘。
