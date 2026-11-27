# 960fce43 · glibc 发行候选的上游源码暂存

`stage_glibc_release_supplements.py --glibc-source` 将 SDK 一致的上游
`glibc-2.44.tar.xz` 加入冻结候选的外层分发。它从绑定的 SDK 归档读取源码验证
回执、已审查的源码锁、签名与公钥，并用 `gpgv` 验证暂存的实际字节。
外层清单 v2 登记原档和 SDK 验证材料，完整校验表覆盖新增资产。省略参数仍生成
原有 v1 暂存结果。冻结候选的原四份归档与清单可直接复用。

```sh
python3 -B scripts/stage_glibc_release_supplements.py \
  --release "$FROZEN_RELEASE" \
  --components "$COMPONENT_SOURCES" --component-manifest-sha256 "$COMPONENT_MANIFEST_SHA256" \
  --xypm-relink "$XYPM_MATERIAL" --xypm-manifest-sha256 "$XYPM_MANIFEST_SHA256" \
  --glibc-source "$GLIBC_ARCHIVE" --output "$STAGED"
```

在接收目录合并原发行与暂存文件，以外层 `CHECKSUMS.sha256` 核对全部资产。
解出 `application-sdk.tar.gz` 后可在已审查的源码树运行签名核对。签名和公钥
与 SDK 实际构建时绑定的字节一致。

```sh
port="$RECEIVER/application-sdk/sdk/sysroot/usr/share/xos-glibc/port"
python3 -B scripts/verify_glibc_source.py \
  --archive "$RECEIVER/glibc-2.44.tar.xz" --signature "$port/keys/glibc_2_44.tar.xz.sig" \
  --key "$port/keys/release_2_44.asc" --output "$VERIFY_OUTPUT"
```

断网 Linux 上，用 `960fce43` 发行初始归档实际运行两次 v2 暂存，外层清单和校验表
字节一致，glibc 原档也逐字节一致。单字节改动的同尺寸原档被拒绝，没有生成输出。
旧参数再生成的 v1 清单及校验表与原候选一致。接收方从新暂存原件重新验证上游签名。
[源码暂存回执](../reports/glibc_v2_release_upstream_source_20261127/manifest.json)

此项补齐 glibc 上游原档本体。其余静态程序的可替换材料和 GNU 供体的历史宿主
路径仍按[默认发行验收表](../releases/glibc_default_gate.md)处理。本次无需重编
运行库或重打原候选，也未执行正式发布。
