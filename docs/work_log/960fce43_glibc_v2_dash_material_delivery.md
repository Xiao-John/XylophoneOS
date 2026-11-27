# 960fce43 · 同版发行 Dash 重链接归档暂存

上游 glibc 原档的 v2 暂存入口增加一对可选参数
`--dash-relink` 与 `--dash-manifest-sha256`。入口使用已验的 Dash 独立归档，
核对其绑定的发行清单、安装器、SDK、应用 profile、Dash ELF 及资料逐项摘要。
归档原字节加入外层清单 v3，完整资产表增加 `dash-relink.tar.gz`。
缺少任一参数时拒绝执行，省略两项保留既有格式。

```sh
python3 -B scripts/stage_glibc_release_supplements.py \
  --release "$FROZEN_RELEASE" \
  --components "$COMPONENT_SOURCES" --component-manifest-sha256 "$COMPONENT_MANIFEST_SHA256" \
  --xypm-relink "$XYPM_MATERIAL" --xypm-manifest-sha256 "$XYPM_MANIFEST_SHA256" \
  --glibc-source "$GLIBC_ARCHIVE" \
  --dash-relink "$DASH_TAR" --dash-manifest-sha256 "$DASH_MANIFEST_SHA256" \
  --output "$STAGED"
```

断网 Linux 接收方用真实 `960fce43` 候选暂存后，Dash 归档仍为 8,566,471 B，
SHA-256 为 `d33d07b4e25d7cb3e7424ac2c67dcb92a055ad6e225262311ee15d31e35fe5c3`。
独立目录按外层 `CHECKSUMS.sha256` 核对了 12 项。验证器拒绝错误清单摘要、
不属于该发行的 Dash，以及在清单不变时修改的单个链接对象。省略新增参数后，
v2 清单与此前已验版本逐字节一致。
[分发清单及接收方回执](../reports/glibc_v2_dash_material_delivery_20261127/manifest.json)

客体证据沿用完全相同的安装器与 Dash 材料，覆盖冷启、原版、替换版及资源回收。
[Dash 实际重链与客体](960fce43_glibc_v2_dash_relink.md)

本次生成的是留存候选及接收材料。其余日用程序、CPython 和 GNU Make 的替换
继续单独验证，正式发布仍由发行门处理。
