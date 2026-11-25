# glibc 来源签名闭环与构建准入

2026-11-25。范围：G4 的来源真实性先决项；基于 PR #153
`07695514b01f004e53bd4355fae93b1d4f3b15a5`。G1–G3 的实现依赖继续沿
#149 → #151 → #152 → #153；#142/#148 的历史由 #149 保留，#150 是早期交接记录。
本项只改来源锁、构建准入及其测试，不更换 XOS 默认 libc，也没有新的运行时 ABI。

## 核验与决策

glibc 2.44 原始归档保持 20,620,544 字节，SHA-256 为
`37f600f2bef3c5e8300147059568b2a2e40a7ad6ccc65ce942556d49429cc667`。
从 GNU 官方 HTTPS 入口取得的 detached signature 与原候选签名完全相同：
`44aabe605a02a56959bab51b92d985945db66dbd0117debe3d741252b2133ec6`。
签名时间为 2026-07-25 00:01:04 UTC。

| 证据 | 实际结果与作用 |
|---|---|
| [GNU 官方 keyring](https://ftp.gnu.org/gnu/gnu-keyring.gpg) | 主密钥与签名子密钥身份一致；所携带旧 binding 于 2026-04-06 过期，实际被检查器拒绝 |
| [Gentoo 固定 Manifest](https://github.com/gentoo/gentoo/blob/446726169ce086d8c0c50ffbee0919351ee8969d/sec-keys/openpgp-keys-glibc/Manifest) 及同提交 ebuild | SHA-512 与 distfiles 上 484,960 字节的密钥文件一致；ebuild 将 glibc 发行密钥关联至维护者 URL；该密钥实际通过签名核验，当前 binding 至 2027-02-10 |
| [维护者当前公钥](https://www.akhuettel.de/key-atwork.txt) | 仍是同一 primary/signing subkey；更新 binding 至 2028-11-14，实际通过 gpgv |
| [独立更新观察](https://keys.openpgp.org/vks/v1/by-fingerprint/35B17DF5752577CA0C541CEB94BFDF4484AD142F) | 观察到相同主密钥、签名子密钥及当前有效期；核验日未观察到这两个密钥的撤销 |

固定主密钥 `35B17DF5752577CA0C541CEB94BFDF4484AD142F`，发行签名子密钥
`FD19E6D31B192EE4DC63EAD3DC2B16215ED5412A`。仓库保存当前公钥的
`export-minimal` 结果与 detached signature；原下载哈希、独立来源和更新策略
均记入 `source_lock.json`。没有回拨时钟或忽略过期状态。
公钥属于公开验证材料，Gentoo 对对应密钥包标注 public-domain；原声明来源保留。

## 实现

`scripts/verify_glibc_source.py` 固定 archive/signature/key 的 SHA-256，使用隔离
空 GNUPG home 和指定 keyring 调用 gpgv，核对唯一 GOODSIG/VALIDSIG、完整
primary/signing fingerprint、签名类型与 SHA-2 摘要算法。过期、撤销、未知
密钥、坏签名和非零工具退出均失败。验证前后再次核对所有输入及工具二进制，
日志保留原始字节，验证目录拒绝覆盖。

`build_glibc_sdk.py` 在源码解包前强制执行该检查；来源结果、验证报告哈希、
公钥、签名及检查脚本随独立 SDK 的 provenance 材料交付。旧 `glibc_g1_signature_diagnostic.py`
保留其历史诊断用途。来源真实性的完成与运行时/应用验收分别记录。

## 实际验证

环境使用 `xos-glibc-sdk-preview` 工具：gpgv 2.2.40、GCC/G++ 16.2.0；
宿主 GnuPG 2.4.7 用于公钥检查和最小导出。

- `tests/glibc_source_auth.py`：5/5，通过实际 gpgv 验证，并分别拒绝归档、
  签名和公钥的单字节篡改；已有验证证据目录保持完整。
- 独立 Gentoo 密钥对相同 tar/signature 的 gpgv 验证通过。
- GNU 旧 keyring 实际得到 `EXPKEYSIG`，检查器返回失败。
- `build_glibc_sdk.py --prepare-only`：通过真实来源准入、全部补丁应用和
  `x86_64-unknown-xos` 配置；最终输入为 182 个受跟踪文件。
- `tests/docs_consistency.py`：通过，78 个已分配 syscall；Python 编译检查通过。

| 原始证据 | SHA-256 |
|---|---|
| `build/source_auth_tests/report.json` | `1eb85b08edae94dcf927c7dc43dc209b96cb162793b8186be0f45d0f369f1927` |
| `build/signature_verified_final/report.json` | `a5165d03e516c7fce06c2fc2fe1de3b65ada6a650f1b26038b86f90bfc1b4b27` |
| `build/authenticated_configure_final/manifest.json` | `79e27720a55d9d612fef03fc70a2d7996b50c19e8582bb20c79e2c984cae2fc5` |

重放（在 preview SDK 环境内，输出须为新目录）：

```sh
python3 scripts/verify_glibc_source.py --archive "$GLIBC_ARCHIVE" \
  --output build/glibc_source_auth
python3 tests/glibc_source_auth.py --archive "$GLIBC_ARCHIVE" \
  --output build/glibc_source_auth_tests
python3 scripts/build_glibc_sdk.py --archive "$GLIBC_ARCHIVE" \
  --output build/glibc_authenticated --prepare-only
python3 tests/docs_consistency.py --output-dir build/glibc_auth_docs
```

## 后续验收

本模块没有重新运行完整 libc 编译或客体套件，改变的是构建准入。后续 G3/G4
组合需用更新来源锁重建独立 SDK，执行其实际受影响的客体用例；原 #151–#153
冻结结果保留在各自输入上。libstdc++、xypm 双 profile、应用迁移及完整发行材料
在后续模块分别交付。更新密钥或发布发行包时重新检查当前撤销与身份来源。

## PR #154 评审跟进：来源快照与证据一致性

2026-11-25，逐条核对评审意见后补入：固定使用预检记录的 gpgv 绝对路径；
锁文件用同一次读取的字节生成信任记录与摘要；归档、签名和 key 均先捕获字节，
gpgv 验证私有副本，解包使用同一不可变归档字节，不再重新打开下载路径。
准备模式与完整构建在成功前共用输入/工具终检；SDK 内部 provenance 同步保存
原始 verification report 摘要。README 明确离线撤销信息的材料边界和发布前更新。

实际重验：有效签名/三种输入篡改/已有证据文件集合与摘要保持，共5项通过；
新增真实归档快照测试在验签后替换下载路径，解包的20947个普通文件逐项匹配
已签归档，替换内容、可变缓冲和未验证报告三种解包输入均在写入前拒绝。
prepare-only再次完成configured，预检gpgv与实际验签工具摘要相同，成功终检通过。

公开派生配置摘要与原字节测试报告位于
[glibc_source_review_20261125](../reports/glibc_source_review_20261125/manifest.json)。
最终configure原manifest SHA-256：
`46386dfe123c9dacb281ec2afc497ea6f722e5721183e9266296af0686a0ce47`；
快照测试报告SHA-256：
`43d3254a57b53ea0ca0b8eba64b20c680a6eea5da4a0ff6dc46b9a79dd8afe23`。
旧报告保持原输入绑定。本跟进改变构建来源路径，运行库代码未变；完整SDK和
客体会在后续G4组合构建重新绑定，不使用此前客体结果替代新构建。

复现新增检查：

```sh
"$XOS_SDK_RUN" python3 tests/glibc_source_auth.py --archive "$XOS_GLIBC_ARCHIVE" --output build/source_auth_review_tests
"$XOS_SDK_RUN" python3 tests/glibc_source_snapshot.py --archive "$XOS_GLIBC_ARCHIVE" --output build/source_snapshot_review
"$XOS_SDK_RUN" python3 scripts/build_glibc_sdk.py --archive "$XOS_GLIBC_ARCHIVE" --output build/authenticated_snapshot_configure --prepare-only
python3 scripts/verify_evidence_index.py docs/reports/glibc_source_review_20261125/manifest.json
```
