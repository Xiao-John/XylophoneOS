# 960fce43 · GNU Make 归档暂存与 xypm 替换复验

GNU Make 重链接归档按实际发行清单、初始工作盘、SDK 与应用 profile 绑定。
在完整核对逐文件摘要后，暂存器用冻结 GNU Seed 回执核对盘上 `/usr/bin/gmake`
和实际构建回执。归档原字节加入外层清单 v5。

在 [日用程序暂存](960fce43_glibc_v2_daily_material_delivery.md) 的参数之外追加
`--gnu-make-relink "$MAKE_TAR" --gnu-make-manifest-sha256 "$MAKE_MANIFEST_SHA256"`。

断网 Linux 从同一发行实物暂存，接收目录校验 14 项。8,657,284 B 的 GNU Make
归档 SHA-256 为 `edff196fbed3bdc9be7add78855c8a2d97adf98c8b5c8e1144f9e73c2d9723cb`。
错误清单、外来盘、外来 Seed、与已绑定 Seed 不同的 gmake 引用均被拒绝。
省略 GNU Make 参数重现既有 v4 清单和校验表。
[GNU Make 暂存与实物回执](../reports/glibc_v2_gnu_make_material_delivery_20261127/manifest.json) ·
[GNU Make Xshell、Dash 与错误退出对照](960fce43_glibc_v2_gnu_make_relink.md)

## 同版本 xypm

用当前候选安装 ISO 冷启 512 MiB 稀疏盘，安装并核对 `/usr/bin/xypm`。
随后在同候选普通 ISO 重跑原版和静态替换版的 `--version` 与 `list`。
四次都退出 0，该版本的替换标记仅在替换 ELF 的版本命令出现，资源回到
`129806 / 2 / 0`。工作盘均为私有临时副本。
此前冻结的原版与替换版 ELF 已核对原摘要。本次重跑使用两份原 ELF 及当前
候选的 ISO，替换库构造见[原工作记录](7209d6e4_glibc_v2_release_xypm_relink.md)。

```sh
PYTHONPATH="$PWD/scripts:$PWD/tests" python3 -B "$REPORT/xypm_same_candidate.py" \
  "$OUTPUT" "$EXISTING_ELF_DIR" "$REOPENED_RELEASE"
```

在源树运行该命令。`OUTPUT` 为已创建的独立输出目录，
`EXISTING_ELF_DIR` 提供与回执一致的 `original.elf` 和 `replacement.elf`。
[同版运行器、绑定回执与串口](../reports/glibc_v2_gnu_make_material_delivery_20261127/manifest.json)
