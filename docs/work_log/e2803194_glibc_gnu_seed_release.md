# e2803194 · 将原生 GNU Seed 纳入显式 glibc 发行

基线是已合入 GNU Seed 客体验收的 `8b763ed2`。发行装配沿用 `release_pipeline.sh package`，验证候选的安装 ISO、普通 ISO、dash/xypm、同 profile 的 daily 和 CPython/zlib，可选纳入 IDNA。选用本组 GNU Seed 时，全部内容进入同一工作盘，盘上 1,374 个 Seed 文件和软件包受管文件分别校验。GNU Make 在同一 glibc SDK 上签名重建，复用的原生 GCC/G++、Binutils 保留历史静态运行库。

| 资产 | 绑定内容 |
| --- | --- |
| `images.tar.gz` | 普通与安装 ISO、首次启动工作盘、启动器、安装清单、Seed 清单和发行身份 |
| `application-sdk.tar.gz` | 实际用于客体 C/C++ 的统一 profile 和独立宿主应用 SDK |
| `packages.tar.gz` | 由安装器验收绑定的 daily、同 profile CPython/zlib、选装的 IDNA XPK |
| `gnu-seed-sources.tar.gz` | 冻结 GCC/G++/Binutils 的对应源码、补遗与准确构建清单，GNU Make 锁定源、签名、钥匙环、移植补丁、构建配方及登记许可 |
| `release_manifest.json`、`system_manifest.json`、`CHECKSUMS.sha256` | 系统、包、SDK、发行盘和归档的身份及接收校验 |

发行软件包与 Seed 均绑定实际 SDK。Seed 的物料校验覆盖对象、已发二进制的对应源码、GCC Runtime Library Exception、冻结工具内含的 newlib 声明和 GNU Make COPYING。最终发行的 libc/C++ 运行库及其余静态应用重链接证据继续按发布门验收。
[原生工具验收](59b9081e_glibc_native_gnu_seed.md) · [同 profile 发行包组合](9dd3de65_glibc_release_package_composition.md) · [发行验收表](../releases/glibc_default_gate.md)

## 复现

```sh
scripts/release_pipeline.sh package --release-dir "$RELEASE" \
  --glibc-candidate "$CANDIDATE" --glibc-app-kit "$KIT" \
  --cpython-package "$CPYTHON" --wheel-package "$IDNA" \
  --gnu-seed-donor "$FROZEN_DONOR" --gnu-make-receipt "$GNU_MAKE_BUILD/manifest.json" \
  --gnu-make-sources "$GNU_MAKE_SOURCES"
python3 tests/glibc_gnu_seed_release_preflight.py --release "$RELEASE" --output "$HOST_REPORT"
scripts/release_pipeline.sh smoke --glibc-release "$RELEASE" --output "$GUEST_REPORT" \
  --foreign-package "$FOREIGN_PROFILE_XPK"
```

Seed 参数成组使用。冻结原件目录来自 v0.0.2-1103 的镜像、发行清单和对应源码资产。GNU Make 源目录包含 `make-4.4.1.tar.gz`、`make-4.4.1.tar.gz.sig` 和 `gnu-keyring.gpg`。装配和接收方复验需要 `gpgv`。用四份归档、系统与发行回执及校验表即可重开本组接收验证。已有无 Seed 候选仍保留原有归档形态。

## 验证绑定

本组使用候选系统 `73601d7ff1c68866`、profile `xos-x86_64-glibc-unified-cxx-v1`、装配源码 `e2803194`。正式工作盘来自本组发行配方，SHA-256 为 `4f5885715a722c23f5de86383be385d5ea19897bb87e2a41999ea08f0e162986`。

断网 Linux arm64 接收方复验重开四份真实归档，验证装盘文件、同 profile 数据和归档内 GNU Make 签名。缺项、重复、内容变动及额外文件四种归档检查均按实际错误拒绝。Seed 参数不完整的调用也被拒绝。旧显式候选仍能按原归档集合重开校验。

升级与旧版回退分别保留其已验证工件和报告。P2→P3 同 glibc profile 的升级、回收、故障恢复见专项证据。历史 newlib 镜像、SDK 和盘保留同一冻结标识，GNU Seed 的 1103 原安装 ISO 回退已另盘验证。最终候选切换默认之前仍需用选定的完整发行输入复跑升级与中断恢复。
[跨版本升级](3ce98ac7_glibc_g4_xypm_p2_p3.md) · [1103 回退实测](59b9081e_glibc_native_gnu_seed.md#客体证据)
