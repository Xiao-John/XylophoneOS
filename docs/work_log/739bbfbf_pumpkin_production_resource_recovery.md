# 739bbfbf · Pumpkin 生产具名资源的重启恢复

本轮从主线 `ebb8a409` 重建独立提供者配置。正式部署 guest gate 按镜像清单选定
具名资源或仅登录模式，复用提供者、监督器、真实 files 租约、独立 broker 和普通
持有者。延续不同 Linux UID 的部署身份隔离与私有凭据入口。
[部署配置](../contracts/pumpkin_provider_deployment.md)

## 验收条件

提供者与客体临时状态分别置于两块独立挂载，由 Linux `findmnt` 确认两者为 ext4。
使用断网 Linux arm64、x86-64 QEMU 11.1.3 TCG 和实际构建的两份不同安装域镜像。
镜像、SDK、源输入、runner 和实际回执的摘要均有记录。产物只含确认结果和摘要。

```sh
env XOS_LWIP_SOURCE_ARCHIVE="$LWIP_ARCHIVE" python3 -B scripts/build.py --output-dir "$SYSTEM" \
  --pumpkin-anchored-probe --pumpkin-native-login --pumpkin-user-login \
  --pumpkin-user-resource --pumpkin-named-resource-store \
  --pumpkin-deployment-realm "$INSTALLATION_REALM"

TMPDIR="$GUEST_FILESYSTEM" python3 -B tests/pumpkin_provider_deployment_guest.py \
  --system "$SYSTEM" --provider-filesystem "$PROVIDER_FILESYSTEM" --output "$OUTPUT"

python3 -B tests/pumpkin_generation_authority_host.py
python3 -B tests/abi_doc_consistency.py
```

仅登录回归使用另一新安装域。构建选用 `--pumpkin-anchored-probe`、
`--pumpkin-native-login`、`--pumpkin-user-login` 和绑定安装域的选项。每次使用新
工作盘。提供者进程保持既有受信管理边界，夹具只在确认原进程退出后清除残留套接字。

## 观测

具名镜像 `89a7a3c46a4d912f` 的 32 项实测通过。首次发放到修订 2，发布在修订 3。
强制退出提供者后盘外记录逐字节相同，残留套接字上的登录请求失败。重新启动真实
提供者和客体后，原持有者读回同一对象的值。替换到修订 4 后，只替换为旧客体盘会被
拒绝，失败启动前后旧盘字节一致。恢复现盘可读替换值，旧对象键及旧代际删除均被拒绝。
在修订 5 删除后重启两个进程，确认对象仍已删除、凭据文件身份保持、普通持有者可登录。
现有监督器和 broker 的完成边界继续约束各个真实客体操作。

同一源码重新构建的仅登录镜像 `ff4077d72bee4820` 通过 19 项原有部署检查。
宿主独立代际九项和 ABI 表检查通过。物理断电、整机与硬件代际仍需相应介质资格。
[工件绑定与回执](../reports/pumpkin_production_resource_recovery_20261127/manifest.json)
