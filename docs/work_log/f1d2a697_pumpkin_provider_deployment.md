# f1d2a697 · Pumpkin 独立代际提供者部署

2026-11-27。以主线 `8d1b985d` 组成验收源码 `6aad67e3`。由编译配置锁定唯一
安装域。部署 profile 同时固定镜像清单、安装域、提供者地址及两个不同的 Linux UID，
启动者与提供者在私用 Unix 套接字上核对真实对端和 profile 摘要。镜像经校验后封存，
QEMU 在固定只读描述符上加载其实际字节。独立提供者先显式创建空记录，再启动读和比较
发布服务。部署启动者只使用此服务，现有客体 files 私有槽、监督器登记权和普通持有者
认证流程继续工作。没有新增内核 ABI。
[部署契约与运行步骤](../contracts/pumpkin_provider_deployment.md)

## 真客体

从实际 Git 源重新构建，使用锁定 lwIP 归档。部署、旧开发、普通镜像分别为
`e02cb7a2acbc1071`、`172a5b7ffafa60b3`、`7503e43bbd1bd127`。

在 Linux arm64、QEMU 11.1.3 TCG、无网络、三个互异非 root UID 的夹具下通过
19 项。首次发放确认修订 1、2 后交付 0600 凭据文件，真实重启通过普通持有者登录。
提供者重启后保留同一修订，单独还原旧客体盘会被拒绝，恢复现盘即可再次登录。
重复请求、错镜像绑定、错误 profile 摘要、错误的操作者与提供者 UID 及提供者缺失
均保持应有状态。验证镜像封存不可写，并确认操作者无法直接读取提供者代际文件。

测试需在隔离 Linux 环境以 root 启动夹具，目标进程由夹具分别切换至配置 UID。
两个路径分别指向仅用于试验的本地代际文件系统和临时客体工作盘区域。测试产物只
记录结果及摘要，私用串口和凭据没有录制。

```sh
python3 -B tests/pumpkin_provider_deployment_guest.py --system "$DEPLOYED_SYSTEM" \
  --provider-filesystem "$DISPOSABLE_PROVIDER_FILESYSTEM" --output "$DEPLOYMENT_REPORT"
python3 -B tests/pumpkin_user_login_guest.py --system "$LEGACY_SYSTEM" --output "$LEGACY_REPORT"
python3 -B tests/pumpkin_generation_authority_host.py
python3 -B tests/pumpkin_host.py
python3 -B tests/abi_doc_consistency.py
```

旧开发入口在 macOS QEMU 11.1.2 通过 19 项，覆盖原首户、凭据错误、重新启动、吊销与
结果不明。普通 Xsh 镜像使用同一 QEMU 启动，`images` 无私有代理、daemon 和 holder，
执行这三个保留名字均得到 `exec: unknown image`，资源保持 `129696 / 3 / 1`。
宿主代际 9 项、核心及 ABI 检查通过。

## 独立文件系统边界

Linux 容器原生可写层耗尽，未能分配代际文件。在同机的 Docker Desktop 宿主共享目录
中，提供者能创建、同步和读回正确记录。另一个 Linux UID 也能读取权限看似私有的记录，
因此这次试验拒绝该共享目录。成功的双 UID 客体门使用两个隔离 Linux tmpfs，分别保存代际
和测试工作盘。真实提供者与客体进程均重启，保持同一代际文件系统；这测定了进程和工作盘
边界。宿主断电、生产磁盘、固件认证、物理控制台、外部钱包保管及硬件代际仍待专项验收。
此前独立代际文件的 APFS 持久提交测试属于另一配置。
[源码绑定、客体证据与环境观察](../reports/pumpkin_provider_deployment_20261127/manifest.json)
