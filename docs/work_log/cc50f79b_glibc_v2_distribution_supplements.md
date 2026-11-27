# cc50f79b · glibc v2 发行候选补充材料暂存

新增入口按原清单核对冻结候选的四份归档、系统清单和原校验表。补充源码和
xypm 重链接材料必须指向同一发行清单，xypm 同时绑定发行 SDK 和实际程序。暂存
外层清单、补充源码归档及清单和 xypm 重链接归档，生成覆盖全部资产的校验表。
老归档和原发行清单继续作为发布输入，不需要重新打包整盘。

```sh
python3 -B scripts/stage_glibc_release_supplements.py \
  --release "$FROZEN_RELEASE" \
  --components "$COMPONENT_SOURCES" --component-manifest-sha256 "$COMPONENT_MANIFEST_SHA256" \
  --xypm-relink "$XYPM_RELINK" --xypm-manifest-sha256 "$XYPM_MANIFEST_SHA256" \
  --output "$SUPPLEMENT_STAGING"
```

冻结目录提供四份归档、release_manifest.json 和 system_manifest.json。暂存目录
提供三份补充资产、distribution_manifest.json 和新的 CHECKSUMS.sha256。
接收方从可信发布记录核对清单摘要后，将两处的文件置于同一目录运行
`sha256sum -c CHECKSUMS.sha256`。原目录的校验表只校验原配方产物。

用冻结 v2 资产实跑两次暂存，五份输出字节一致。十份资产分别读回并校验摘要。
两个补充清单的错误摘要均被拒，未产生输出目录。源码归档通过 135 项接收核对。
xypm 归档在断网 Linux 容器内解包，使用归档自身的复链命令，得到与该发行 ELF
一致的 SHA-256。GNU ld 报出现有的 raise 占位提示，既有 xypm 客体结果见专项。

[资格与计算摘要](../reports/glibc_v2_distribution_supplements_20261127/manifest.json) ·
[断网 xypm 客体](7209d6e4_glibc_v2_release_xypm_relink.md)

本次交付范围是候选发行资产暂存。发布、CPython/zlib 独立重建和其余静态程序
的替换材料仍需验收。
