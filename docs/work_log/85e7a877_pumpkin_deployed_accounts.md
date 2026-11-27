# 85e7a877 · Pumpkin 独立提供者的多账户验收

候选基于主线 `0227427a`。部署夹具以 `--multiple-accounts`
在原有具名资源恢复门之后继续验证第二个账户。沿用受信操作者、
独立 Linux UID 的代际提供者、封存的 ISO、XOS 监督器、私有 files 租约及
资源 broker。两个账户使用各自的私有钱包。

## 客体结果

具名镜像 `fbe70625e73497ca` 在断网 Linux arm64 容器的 QEMU 11.1.3 TCG 上
通过 44 项检查，其中 32 项覆盖原单账户部署和资源恢复。客体状态与提供者记录使用
两个分别挂载的 ext4 卷。两个钱包绑定同一安装域的账户序号 1 和 2，分别以 `0600` 权限发行。重复登记与错配钱包被拒，未改变已提交代际。

第二个账户在修订 6 登记，具名对象在修订 7 发布给该账户。第一个账户仍能建立会话，
读取该对象被 broker 拒绝。受信操作者在修订 8 吊销第一个账户后，重启独立提供者以及
客体。第一个账户的普通认证和具名读取均被拒，第二个账户仍可独立登录并读回修订 7
对象。两个钱包的文件身份、大小和修改时间保持。只登录镜像 `71e4bd946dd9e2e1`
使用新安装域，通过原有 19 项部署检查。宿主代际、ABI 表和 10 项许可材料检查通过。
[镜像、SDK 和脱敏回执](../reports/pumpkin_deployed_accounts_20261127/manifest.json)

第一次重建通过前 23 项，在提供者强退之后的读回步骤于宿主临时目录作用域发生
`OSError`。当时夹具依次复制两个逻辑大小各为 512 MiB 的客体磁盘，卷清理后可用空间
约 695 MiB。夹具改为复用已有的稀疏快照函数，复制后核对全盘字节摘要；
重新构建后在同两块卷完成原失败步骤和后续检查。验收范围为受控 Linux/QEMU 部署，
物理启动、物理断电及硬件代际源仍待独立实测。

## 重跑

选择锁定的 lwIP 源包、已存在的两个 ext4 挂载及新安装域。公开回执从私有原件派生，
同时保留原件 SHA-256。

```sh
XOS_LWIP_SOURCE_ARCHIVE="$LWIP_ARCHIVE" python3 -B scripts/build.py --output-dir "$SYSTEM" \
  --pumpkin-anchored-probe --pumpkin-native-login --pumpkin-user-login \
  --pumpkin-user-resource --pumpkin-named-resource-store --pumpkin-deployment-realm "$NAMED_REALM"
TMPDIR="$GUEST_FILESYSTEM" python3 -B tests/pumpkin_provider_deployment_guest.py \
  --system "$SYSTEM" --provider-filesystem "$PROVIDER_FILESYSTEM" --output "$OUTPUT" --multiple-accounts
```

宿主执行 `tests/pumpkin_generation_authority_host.py`、
`tests/abi_doc_consistency.py --output-dir "$AUDIT"` 及
`scripts/license_audit.py --build "$SYSTEM"`。

只登录回归使用另一新安装域，构建省略 `--pumpkin-user-resource` 和
`--pumpkin-named-resource-store`，运行省略 `--multiple-accounts`。
