# 960fce43 · 发行 GNU Make 的独立重链接

从发行工作盘以只读方式导出 `/usr/bin/gmake`。工作盘、GNU Seed 回执、实际
生产构建回执与发行清单 `fd95e47c…e588` 一致。盘上 ELF 与 GNU Make 4.4.1
生产 ELF 的 SHA-256 均为 `793e6b79…0ebe`。其已验签上游源码、补丁和许可
随同版 GNU Seed 源码归档提供。

收集使用由生产回执绑定的原始编译日志和最终链接命令。保留按实际顺序链接的
30 个 GNU Make 对象、`libgnu.a`、链接脚本、启动与结束对象及 SDK 库档。
接收工具保留生产的 `--gc-sections`，验证全部文件和交叉工具摘要。从仅挂载归档及
测试脚本的断网 Linux 接收环境执行原版重链接，逐字节复现了发行盘中的 GNU Make。
[生产绑定和实物对照](../reports/glibc_v2_gnu_make_relink_20261127/host.json)

测试库在保留原 `exit` 行为的同时增加一条标准错误标记。比较 `libc.a` 的
1,686 个有序成员及内容，只有 `exit.o` 发生变化。接收入口拒绝错误库摘要且未
产生输出，随后使用正确摘要得到不同的 GNU Make ELF。

同一专用稀疏 FAT32 盘用冻结发行普通 ISO 冷启两次，分别验证原版和替换版。
两版都报告 4.4.1，都能从 Xshell 执行带变量及文件依赖的 recipe。从 Dash
调用后重建结果文件，两版读回均为 `linked dash`。失败 recipe 的 `exit 7`
仍使两版 GNU Make 以状态 2 退出。替换版每项命令打印一次退出标记，原版无标记。
每项操作的空闲页、任务数和完成队列都恢复到各自基线。
[客体回执及原始串口](../reports/glibc_v2_gnu_make_relink_20261127/manifest.json)

| 接收输入或产物 | SHA-256 |
| --- | --- |
| 本地材料归档，8,657,284 字节 | `edff196fbed3bdc9be7add78855c8a2d97adf98c8b5c8e1144f9e73c2d9723cb` |
| 归档内清单 | `e4f7b7fdb778e042ac012f0ef5b7fa60d27f799aeaf59d8b7c710626589f2e1e` |
| 发行 ELF 与原库重链接 ELF | `793e6b79d866e42b2633f462c59afc72cd7c716e6e5e7609bcf7e998e58a0ebe` |
| 测试库重链接 ELF | `573e1c4c30fc6d16e0fa140aaac036da2465d5c36ee656ffde7f89bcb97d25de` |

## 复验

`RELEASE` 指实际发行解包目录，应带原工作盘、GNU Seed 回执和应用 SDK。
`MAKE_BUILD` 指保留 `manifest.json`、`compile.log` 和 `target/` 的
生产构建目录。收集器只读访问原工作盘。另用独立 `OUT` 保存材料。

```sh
RELEASE_SHA=fd95e47c8f99205f1ff1ec6ac77537e00b9f7a46d77046d787ae4d03c361e588
mkdir -p "$OUT"
python3 -B scripts/collect_release_make_relink.py \
  --release "$RELEASE" --build "$MAKE_BUILD" --sha256 "$RELEASE_SHA" \
  --output "$OUT/materials"
tar -C "$OUT/materials" -czf "$OUT/gnu-make-relink.tar.gz" .
```

为断网 Linux 接收方提供材料归档 `ARCHIVE`、发行方给出的归档和清单摘要，
以及对应的目标交叉工具。独立封装归档时重新计算外层摘要。

```sh
bash tests/glibc_release_make_relink_receiver.sh \
  "$ARCHIVE" "$ARCHIVE_SHA" "$MATERIALS_SHA" "$OUT/linked"
```

把两份 ELF 带到 QEMU 验收环境，`DASH` 指发行清单绑定的同版 Dash ELF。
运行器只新建一个稀疏测试盘，不复制发行工作盘。

```sh
REPLACEMENT_SHA=573e1c4c30fc6d16e0fa140aaac036da2465d5c36ee656ffde7f89bcb97d25de
python3 -B tests/glibc_release_make_relink.py --release "$RELEASE" \
  --release-sha256 "$RELEASE_SHA" --dash "$DASH" \
  --original "$OUT/linked/original.elf" --replacement "$OUT/linked/replacement.elf" \
  --replacement-sha256 "$REPLACEMENT_SHA" --output "$OUT/guest"
```

本次资格覆盖这版发行盘中的 GNU Make。归档需纳入同版补充资产，与已验签 GNU Make
原件和同版 glibc 源码一同提供。测试库仅用于接收复验。
