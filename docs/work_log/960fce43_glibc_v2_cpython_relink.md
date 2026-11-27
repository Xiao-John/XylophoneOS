# 960fce43 · 发行 CPython 的独立重链接

以冻结发行清单 `fd95e47c…e588`、实际 CPython 3.14.9 XPK `24791dcf…9740b`
及内部包回执 `73512041…4d39` 为基线。该包绑定串行 CLI 回执
`11ead1c1…6c` 和去调试段前后的两个 ELF 摘要。原始 CPython、zlib、来源锁定与
补丁由对应 [组件源码材料](9c747f60_glibc_v2_component_sources.md) 提供。

实际保留的对象来自先前双任务构建。它的完整构建日志与串行发行日志摘要不同，
两者最终 GCC 参数逐项相同，共 281 项，两个未剥离解释器的摘要一致。
收集器从只读对象目录保留 227 个 CPython 对象、XOS 时间桥接、zlib 档和
实际使用的 8 个 CPython 库档，再补齐由 v2 SDK 回执绑定的启动对象、脚本和库。
原命令直接使用对象，归档无需重复收录 `libpython3.14.a`。计划保留重复出现
的链接输入及其顺序，并将 `-l` 参数解析到同版 SDK 库档。

在单 CPU 断网 Linux 中，只用材料归档及绑定工具重链接，得到与发行回执相同
的 46,754,232 字节调试 ELF，再用同版 `objcopy --strip-debug` 重现 XPK 中
9,503,392 字节的解释器。剥离前后的加载段和静态 TLS 一致。对象和完整调试
ELF 均在私有 tmpfs 内处理，只保留压缩档、两份 runtime ELF 和回执。
[宿主绑定、链接与替换回执](../reports/glibc_v2_cpython_relink_20261127/manifest.json)

测试复制 `libc.a`，仅替换 `exit.o`。替换对象在委托原退出逻辑前打印标记。
1,686 个档成员同序比对，仅此成员字节改变。给错替换档摘要时，接收入口拒绝
并保持目标不存在。实际使用该库重链接得到不同的解释器。

用当前发行普通 ISO 和同一专用稀疏盘分别冷启原版、替换版。两版都使用从实际
XPK 提取的原始 `python314.zip` 与 `os.py`。两轮均通过版本、装载标准库、
zlib 流、gzip、deflate ZIP、zipimport、截断和校验失败检查。运行缺失脚本
仍返回状态 2。替换版每项恰好输出一次退出标记，原版无标记。
两轮生成的 gzip、ZIP 和原标准库逐项离线核对，资源计数恢复。
[客体回执及原始串口](../reports/glibc_v2_cpython_relink_20261127/manifest.json)

| 接收输入或产物 | SHA-256 |
| --- | --- |
| 本地材料归档，34,036,201 字节 | `9e3b36125d26f46e93e06e3f07a4f79dc351e0503fffed3f126170e7f9d93c20` |
| 归档内清单 | `9efca394a6775b17560b3db0b62dd45fe0244af5ee447877ff10f3715e389ac8` |
| 发行调试 ELF 与原库重链接 ELF | `bde479d98782affbe2eb9013a21a4485893a89deb92385a01ff947df195497ad` |
| 发行 runtime ELF 与原库重链接 runtime | `f778ec71ab3c9808cf63c7e05e7631eb5cc4c7e300c81d112fe0e3026efe0d16` |
| 测试库重链接 runtime | `9cab8de40ca1c842c1057f89cbec30a992ac338ca56922298649b83d9b208b6c` |

## 复验

`RELEASE` 指实际归档解出的发行目录。`DONOR` 指保留
`py0a_report.json`、`target_make.log`、`target_build/`、`xos_time.o` 和
`zlib/lib/libz.a` 的对象树。`FROZEN` 指保留发行串行构建 `cpython-cli.json`
和 `target_make.log.gz` 的目录。三个输入均可只读挂载。

```sh
RELEASE_SHA=fd95e47c8f99205f1ff1ec6ac77537e00b9f7a46d77046d787ae4d03c361e588
python3 -B scripts/collect_release_cpython_relink.py --release "$RELEASE" \
  --donor "$DONOR" --frozen "$FROZEN" --sha256 "$RELEASE_SHA" \
  --output "$OUT/cpython-relink.tar.gz"
```

为断网 Linux 接收方提供 `ARCHIVE`、发行方给出的归档和清单摘要，
以及对应的交叉工具。接收方的工作目录应有足够空间容纳约 130 MiB
解包材料和临时调试 ELF。

```sh
bash tests/glibc_release_cpython_relink_receiver.sh \
  "$ARCHIVE" "$ARCHIVE_SHA" "$MATERIALS_SHA" "$OUT/linked"
```

将两份 runtime ELF 提供给普通 QEMU。运行器从同版 XPK 提取测试用标准库，
启动两次，退出时清理专用测试盘。此项复验覆盖解释器及其打包库的运行；
真实 XPK 的安装、升级和卸载已有单独
[客体验收](458f4933_glibc_v2_cpython_stock_guest.md)。

```sh
REPLACEMENT_SHA=9cab8de40ca1c842c1057f89cbec30a992ac338ca56922298649b83d9b208b6c
python3 -B tests/glibc_release_cpython_relink.py --release "$RELEASE" \
  --release-sha256 "$RELEASE_SHA" --original "$OUT/linked/original.elf" \
  --replacement "$OUT/linked/replacement.elf" \
  --replacement-sha256 "$REPLACEMENT_SHA" --output "$OUT/guest"
```

此归档随同版组件对应源码和 glibc 原档交付。替换版本仅用于接收复验。
