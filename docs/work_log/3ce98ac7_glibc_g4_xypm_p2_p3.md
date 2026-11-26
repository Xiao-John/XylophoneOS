# 3ce98ac7 · glibc G4 xypm P2 到 P3 跨版本

`v0.0.2-1103` 的发布构建源码为 `6fe330ce2dd9441d72da611c1f87b80dad8e3b03`。其 xypm 源码和打包配方与本地发行标签 `071330f3` 一致。原始程序显示 `xypm 0.3 (P2 transactions)`，发布配方继承包管理工具的 `0.1.0` r0。P3 的发布配方和客体版本则分别为 `0.4.0` r0 和 `xypm 0.4.0 (P3 offline repositories)`。初始盘的数据库、索引和三个受管包由客体中的 P2 程序创建。用户文件由当时客体的 Xsh 编辑器写入并同步。

## 旧发行盘兼容边界

从本地缓存重解 1103 SDK，以当时的原始配方重建旧 xypm，同时从同一发行源码重建早期 `xos.img`。归档 SHA-256 为 `cfcec9812a7e592cc820f307e109f38719b03de10be4f658957f916ba8c82209`，与缓存 `CHECKSUMS.sha256` 一致。仓库发行页回执记录了不同 SDK 归档哈希 `9c591f8b…`。缓存的 `release_manifest.json` 和仓库回执具相同哈希 `8288138e…`，SDK 中 `include/`、`lib/`、`cpp/`、`crt0*.o`、`user.ld` 及 SDK manifest 共 1029 个编译输入均逐项符合该发行清单。缓存归档包含有差异的开发文档和宿主工具。隔离测试 profile 在相同 ID 下登记此完整解包树的 `d60552ff…`，原 profile 本身仍只有既有绑定。以实际镜像 `7cc38437aa823d84` 和重建 ELF 为证。本地缓存没有原发行镜像，发布回执所列原版 `8356e45af316fc93` 的镜像及内附 ELF 仍未复验。

用当前镜像冷启旧盘副本并运行 glibc P3。新 xypm 可执行，真实 `upgrade` 在读取旧数据库时返回 `installed database profile mismatch`。Xsh 临时保留维护门，随后 `maint-recover-boot` 报告 `no transaction` 并释放门。旧数据库、索引、包载荷和用户文件与旧客体创建时一致。扣除当前镜像在启动期间写入的普通数据，拒绝盘和同配置、同输入的仅启动对照盘全盘 SHA-256 一致。再用旧镜像冷启已拒绝的盘，旧管理器仍报告 0.3，并可查询依赖包和读回用户数据。

跨 libc 工作盘继续受单 profile 规则约束。现有支持路径是保留旧盘或在目标 profile 用重建的包建立独立盘，应用数据按其契约带入。xypm 的本次资格不包括跨 profile 的受管文件或数据库转换。
[profile 契约](../contracts/xypm_sdk_profiles.md)

## 同一 glibc profile 的支持范围

将 1103 的 P2 代码用已核验源码签名的 glibc C/C++ SDK 重建。仅回移进入维护会话的 FILES 客户端接线（`73305240`）与目录删除明确授权的调用（`fb5f5331`），保留原 P2 包版本、事务、数据库、索引和日志格式。用 `aa267bfe` 重建的普通离线镜像 `b74c9dec2c92c9bd` 运行 P2 和 P3。原生 P2 从空盘创建 `db.json` 格式 1 和 `xypm-index-v1`，并持久化依赖包的版本、修订和 XPK 摘要。新 P3 另支持仓库索引和仓库锁格式 1。仓库锁由同两份依赖包生成，P2 对新增命令返回不支持，P3 冷启动后可验证闭包及相关摘要。

0.4.0 正常工具按固定 XPK 摘要进行升级。操作前后资源计数均为 `129806 / 2 / 0`。另从同一旧盘副本运行 0.4.0 的故障测试构建，定位删除旧版 `/usr/bin/xypm` 后的第 146 个检查点，使用另一个旧盘副本同步中断。停机时旧 ELF 缺失且事务日志在盘。冷启内置恢复器成功回滚，旧版二进制、数据库、索引、依赖锁和用户文件的读回与原旧盘一致。由恢复盘的单独副本重试，冷启后再次验证 P3、仓库闭包和用户数据。正常升级与恢复后重试所得数据库和索引逐字节一致。故障构建仅作为事务执行器，所升级的包始终是正常 0.4.0 XPK。

## 复现

绑定本地安装介质的构建 manifest，使用断网 Linux arm64 容器、GCC 16.2、Binutils 2.47 与 QEMU 11.1.3。以下以当前树为工作目录。`$HISTORICAL_TREE` 检出 `6fe330ce`，`$OLD_SDK` 为本地缓存归档的重新解包树，`$OLD_PROFILE` 是保留原 profile ID 并为测试登记 SDK 目录摘要的私有副本。以该历史树 `scripts/xos_app.py` 的 `tree_receipt()` 计算摘要，先将对应编译输入对照发布清单。`$OLD_RECEIPT` 应可从当前容器读到，回执所列文件路径须同时可用。

```sh
python3 "$HISTORICAL_TREE/scripts/build.py" --output-dir "$HISTORICAL_TREE/build/g4/system"
python3 "$HISTORICAL_TREE/scripts/build_xypm.py" --sdk "$OLD_SDK" --profile "$OLD_PROFILE" > "$OLD_RECEIPT"

mkdir -p build/g4/records
python3 scripts/build.py --output-dir build/g4/system-offline --quiet-demos-on-launch
image=build/g4/system-offline/xos-install.iso
sdk="$GLIBC_KIT/sdk"
profile="$GLIBC_KIT/profile.json"
python3 scripts/build_xypm.py --sdk "$sdk" --profile "$profile" > build/g4/records/new.json
python3 scripts/build_xypm.py --sdk "$sdk" --profile "$profile" --fault-injection > build/g4/records/fault.json
python3 tests/build_xypm_p2_glibc_fixture.py --sdk "$sdk" --profile "$profile" --output build/g4/old-glibc

python3 tests/package_g4_cross_version_guest.py \
  --old "$OLD_RECEIPT" --new build/g4/records/new.json \
  --profile "$OLD_PROFILE" --next-profile "$profile" \
  --old-image "$HISTORICAL_TREE/build/g4/system/xos.img" --new-image "$image" \
  --output build/g4/legacy-test
python3 tests/package_g4_cross_version_guest.py \
  --old build/g4/old-glibc/manifest.json --new build/g4/records/new.json --fault build/g4/records/fault.json \
  --profile "$profile" --next-profile "$profile" --old-image "$image" --new-image "$image" \
  --output build/g4/glibc-test
```

输出保留各阶段的独立工作盘和串口。两次同 profile 完整运行的旧版、正常升级、中断、恢复及重试盘对应摘要一致。宿主 profile 测试 45 项、P3 仓库测试 50 项通过。已核对到交付基线 `af47b2c5` 的相关构建、xypm、文件服务和客体测试依赖没有变化。可恢复退出覆盖同步检查点，断电、扇区撕裂或未知数据库格式仍待验收。先前同版本替换和冻结 newlib 的整盘回退分别有独立证据。本组提供 G4 版本升级和拒绝边界的客体证据，默认 SDK 切换仍由最终组合验收决定。
[本次绑定与客体证据](../reports/glibc_xypm_cross_version_20261127/manifest.json) · [同版本自升级](1ea5a358_glibc_g4_xypm_self_upgrade.md) · [冻结发行盘回退](4ffa226d_glibc_stock_fork_frozen_rollback.md)
