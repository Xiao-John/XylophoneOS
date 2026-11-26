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
工作盘快照、操作者备份和回退流程外。套接字父目录由提供者独占写入，允许
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

受信宿主分别管理启动者和独立提供者，宿主的 root、虚拟化平台及两种角色各自的
同 UID 进程属于其信任范围。接收者钱包仍由受信启动工具保存和提交。此配置目前
按独立受控 Linux 环境验收。正式物理启动和控制台证明、硬件代际或宿主完整回滚
防护、镜像滚动更新、多个启动者、外部钱包保管及物理断电仍需独立验证。
