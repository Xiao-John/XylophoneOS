# Pumpkin 独立提供者部署配置

此配置供拥有受信启动控制权的 Linux 虚拟化管理员使用。它在现有 Pumpkin
原生登录之上增加明确的安装域、镜像授权和一个独立代际进程。客体照常使用
真实监督器、COM1 独占代理和 files 私有槽。普通持有者取得经核验的认证
端点及自己的凭据，对应的登记端点仍只属于监督器。
[凭据入口](pumpkin_user_login.md) · [代际与槽](pumpkin_anchored_files_store.md)

## 部署授权

受信构建者为每个新安装选择独立的非零 16 字节安装域，并在同一镜像中的
监督器、代际代理和守护进程编译绑定。开发配置保留已有安装域和格式。
部署配置使用不同的安装域，且启动工具需要显式提供清单。下面变量
`INSTALLATION_REALM` 取新随机值的 32 位小写十六进制表示。

```sh
python3 -B scripts/build.py --output-dir "$SYSTEM" \
  --pumpkin-anchored-probe --pumpkin-native-login --pumpkin-user-login \
  --pumpkin-deployment-realm "$INSTALLATION_REALM"
```

部署管理员选择两个不同的非 root Linux UID。操作者拥有私有状态目录，独立
提供者拥有代际根和套接字父目录。提供者的代际根仅自身可访问，并须排除在客体、
工作盘快照、操作者备份和回退流程外。存储必须实际执行 Linux 身份隔离。已测 Docker Desktop 宿主共享目录
可报告正确所有者和权限，但仍允许另一 Linux UID 读取，因而不能用作代际存储。
套接字父目录由提供者独占写入，允许
操作者所在受信组遍历。提供者以 `0660` 建立本地套接字，可用父目录的 setgid
继承所选择的组。各上级路径由宿主管理员保护。

管理员从可信渠道交付以下格式的 JSON 和其 SHA-256。摘要须通过已验证的
外部渠道发放或固定在受信宿主的启动配置。路径只定位本机进程。双方使用
Linux 的 `SO_PEERCRED` 核对绑定的对端 UID。[Linux 专用套接字凭据](https://man7.org/linux/man-pages/man7/unix.7.html)

```json
{
  "format": "xos-pumpkin-local-provider-v1",
  "realm": "<与构建匹配的新安装域>",
  "system_manifest_sha256": "<受信镜像的 manifest.json 摘要>",
  "operator_uid": 22101,
  "provider_uid": 22102,
  "provider_socket": "/run/pumpkin/generation.sock",
  "named_resources": false
}
```

格式固定以上七个字段，布尔值需匹配镜像配置。提供者按可信清单选择记录，
每次交换同时匹配清单摘要与内核认证的对端。提供者通道只允许完整的读和
比较发布，失败按代际契约返回未知或停止。用户凭据和账户内容沿用已有专用
客体线路。发布继续要求持有本次操作的文件租约并匹配完整宿主代际。

## 首次发放和下一次登录

提供者 UID 在已建立的私有根内显式预配空记录。开始服务和重新启动服务都
要求此记录可读。服务的工作目录与操作者的工作盘互相独立。正常终止回收
自身套接字，强制终止后由宿主服务管理器确认进程已结束再清理原套接字。

```sh
python3 -B scripts/pumpkin_generation_provider.py provision \
  --profile "$PROFILE" --profile-sha256 "$PROFILE_SHA256" --root "$PROVIDER_ROOT"
python3 -B scripts/pumpkin_generation_provider.py serve \
  --profile "$PROFILE" --profile-sha256 "$PROFILE_SHA256" --root "$PROVIDER_ROOT"
```

以下命令在操作者 UID 下执行。准备阶段读取已确认的空记录，只创建客体工作盘
和部署绑定文件。启动阶段核对绑定文件、镜像及提供者连接，随后执行原有登记
和普通认证。启动器将 ISO 复制到仅传给本次 QEMU 的 Linux 文件描述符，以只读
封存并核对实际启动字节的摘要。首个账户仍需确认修订 1 与 2 才交付凭据。重复首次发放不创建
钱包。提交范围不明时按原有操作手册先复核状态。

```sh
python3 -B scripts/pumpkin_user_login.py prepare --system "$SYSTEM" --state "$STATE" \
  --deployment-profile "$PROFILE" --deployment-profile-sha256 "$PROFILE_SHA256"
python3 -B scripts/pumpkin_user_login.py provision-first --system "$SYSTEM" --state "$STATE" \
  --deployment-profile "$PROFILE" --deployment-profile-sha256 "$PROFILE_SHA256" \
  --credential-file "$PRIVATE_CREDENTIAL"
python3 -B scripts/pumpkin_user_login.py login --system "$SYSTEM" --state "$STATE" \
  --deployment-profile "$PROFILE" --deployment-profile-sha256 "$PROFILE_SHA256" \
  --credential-file "$PRIVATE_CREDENTIAL"
```

## 具名资源部署

构建时在上述部署参数追加 `--pumpkin-user-resource --pumpkin-named-resource-store`，
将匹配镜像的部署清单中的 `named_resources` 设为 `true`。受信操作者用
`publish-named` 创建或替换对象，用 `erase-named` 删除确切代际。普通持有者用
`read-named` 和私有凭据恢复其所有的对象。动作参数和返回值沿用
[原生登录入口](pumpkin_user_login.md) 与 [具名存储契约](pumpkin_named_resource_store.md)。

Linux ext4 上，新盘首次发放后的资源在提供者进程强制退出后保持。管理员确认旧实例
退出并清理残留套接字后，独立提供者与新客体可读回当前对象。仅还原客体工作盘时，
保留的盘外记录会拒绝旧状态。经原生删除后再次重启，持有者仍可建立普通会话。
[ext4 部署与回归回执](../reports/pumpkin_production_resource_recovery_20261127/manifest.json)

受信操作者可用 `enroll --account NAME --credential-file WALLET` 登记后续账户，用
`revoke --account NAME` 吊销指定账户。显式账户选择和钱包适用于登录与具名资源读取。
每个钱包绑定安装域和单个账户序号。具名资源读取同时需要有效会话、所有者身份和当前
对象代际。以下部署回执覆盖两个账户、提供者重启、单账户持久吊销和另一账户持续读取。
[多账户 ext4 部署回执](../reports/pumpkin_deployed_accounts_20261127/manifest.json)

## 检查候选镜像的宿主绑定

操作者可在私有安装上运行只读预检。管理员分别交付当前和候选清单的可信 SHA-256。

```sh
python3 -B scripts/pumpkin_user_login.py check-image-update --state "$STATE" \
  --system "$SYSTEM" --deployment-profile "$PROFILE" --deployment-profile-sha256 "$PROFILE_SHA256" \
  --replacement-system "$NEXT_SYSTEM" --replacement-deployment-profile "$NEXT_PROFILE" \
  --replacement-deployment-profile-sha256 "$NEXT_PROFILE_SHA256"
```

诊断复用普通启动的镜像摘要检查和状态目录非阻塞独占锁。锁作用于已经存在的
状态目录，预检读取当前安装绑定并核对工作盘的文件类型与归属。两份镜像需分别
符合各自的部署清单，同时沿用相同安装域、操作者 UID、提供者 UID、套接字路径及
账户和资源存储配置。成功返回 `bindings_compatible` 和两份系统 manifest 摘要。
此状态只记录宿主绑定。检查期间无需连接提供者，也无需启动客体。客体协议、
工作盘内容、代际连续性和实际切换需要各自的验收。

当前 `deployment.sha256` 和运行中的提供者各自要求匹配一个完整的部署清单
摘要。提供者的 ext4 同步提交覆盖代际记录。镜像切换要在管理员授权的独占维护
窗口协调这两个端点，并让提供者继续使用同一安装域的现有独立代际根。后续实现
须持久记录旧、新摘要及切换阶段，在任一步骤中断后先核对两端和完整代际记录。
只在状态得到确认后恢复启动。状态不明时保留两端和工作盘供恢复，依据独立代际
确认盘状态。
[真实构建预检回执](../work_log/73776af5_pumpkin_image_update_check.md)

同域两张真实 ISO 已在受控 Linux/QEMU 环境使用同一工作盘和独立代际根完成换版与
回切演练。两端绑定错配拒绝，候选读取旧代际并提交新代际，原镜像读回新代际。
受测账户和资源程序使用相同字节。演练夹具负责替换专用测试标记，生产切换控制器及
其中断恢复另验。
[真实客体演练](../work_log/a569d3a6_pumpkin_image_transition_guest.md)

受信宿主分别管理启动者和独立提供者，宿主的 root、虚拟化平台及两种角色各自的
同 UID 进程属于其信任范围。接收者钱包仍由受信启动工具保存和提交。此配置目前
按独立受控 Linux 环境验收。正式物理启动和控制台证明、硬件代际或宿主完整回滚
防护、镜像滚动更新、多个启动者、外部钱包保管及物理断电仍需独立验证。
