# 7ce64487 · Pumpkin durable account resource login

2026-11-26。以已验证的独立 broker 分支 `62d3b26c` 为依赖，实施提交
`528cc319`、`40c9370c`。在保留宿主管道登录和盘外代际保护的开发配置中增加
显式的 `--pumpkin-user-resource` 和 `read-resource` 入口。 [用户凭据与资源契约](../contracts/pumpkin_user_login.md)

监督器从已恢复持久库的登记端读取完整账户身份。独立持有者在实际普通 daemon
端点完成认证并核对同一身份。监督器确认持有者认证后，从内置目录启动 broker，并
经双方内核认证的端点以该身份标记新封存的匿名对象。broker 保有真实 files
打开描述，持有者使用与普通镜像复用的客户端和一次读取关联。核对字节后，持有者
准备下一次读取，正常登出，然后在关联的两秒有效期内确认其被拒绝。监督器在
所有子进程退出且资源计数恢复后才确认操作成功。

初次构建使用的 broker 内置名超过 `image_info.name` 的 16 字节字段，客体上的
精确目录查询无法找到映像。改用 `p2_sealed` 并检查编译期长度。普通版本的 broker
可执行件仍可按原路径启动。存储角色、公开头和系统默认配置无变化。

## 实际运行

QEMU 11.1.2、GNU GCC/G++ 16.2.0、Binutils 2.47。使用独立 QEMU 和一次性
工作盘。受信宿主的凭据文件依旧走私有目录和原打开描述核验。报告仅含通过的场景、
状态与工件摘要。

```sh
python3 -B scripts/build.py --pumpkin-anchored-probe --pumpkin-native-login \
  --pumpkin-user-login --pumpkin-user-resource --output-dir build/resource-system-final
python3 -B tests/pumpkin_user_login_guest.py --resource --system build/resource-system-final \
  --output build/resource-guest-final
python3 -B scripts/build.py --pumpkin-anchored-probe --pumpkin-native-login \
  --pumpkin-user-login --output-dir build/login-only-final
python3 -B tests/pumpkin_user_login_guest.py --system build/login-only-final \
  --output build/login-only-guest-final
python3 -B scripts/build.py --output-dir build/ordinary-combined-final
python3 -B scripts/build_pumpkin_daemon.py --bridge-probe --sdk build/ordinary-combined-final/sdk \
  --output build/ordinary-bridge-final
python3 -B scripts/build_dash.py --sdk build/ordinary-combined-final/sdk --receipt build/ordinary-dash-final.json
python3 -B tests/pumpkin_daemon_guest.py --bridge-probe --system build/ordinary-combined-final \
  --fixture build/ordinary-bridge-final --dash-receipt build/ordinary-dash-final.json \
  --output build/ordinary-bridge-guest-final
python3 -B tests/pumpkin_host.py --sanitize --target-cxx x86_64-elf-g++ --output build/resource-host-final
python3 -B tests/pumpkin_daemon_loop_host.py
```

组合镜像通过 16 项检查。先由真实登记端确认修订 2，使用同一凭据在两个新 VM 各
完成一次封存读取、登出和到期前拒绝。两次读取后盘外完整代际记录与登记后相同；
随后实际吊销推进到修订 3，新 VM 的普通登录和资源入口均返回认证拒绝。凭据文件
的 inode 与修改时间保持一致。原有凭据保护及结果未知回归通过。未启用资源的
登录镜像通过 13 项，资源动作在该镜像的宿主预检中被拒绝。普通镜像的独立 broker
在 xsh 和 dash 下各通过 13 项关联检查，均恢复资源计数 `[129711, 3, 1]`。
ASan/UBSan、目标独立编译及 daemon 回复队列检查通过。

| 工件 | SHA-256 |
| --- | --- |
| 组合系统 `7dc61dc6299b0186` manifest | `1e8dfed019ce5cab79230b85298babb26d3871d5a1beb8e4fda421140885d3a9` |
| 组合系统 ISO | `b6f04a50c394378555d530e1d2666e8021993232e59986fc78c3f3db7bc5206d` |
| 内置 `user_p2_sealed.image.elf` | `5e9bbccc84bb3d9af550ff45fc19b8d0605d2426d04fbdef5968a049d02e4c3a` |
| `build/resource-guest-final/report.json` | `518c4316c95fd8017ab86227111584e596b0f5f3a478843c02773276414b6204` |
| 登录系统 `24a69bcbd5880ca5` manifest | `d40a642fbb06ba3494de420dd1d52be72f73cd56b533c57a424660c30a5c2f3e` |
| `build/login-only-guest-final/report.json` | `7d9d052811dbf35a7b52e312d2656e47a0d8501dec7c627aaa8b92c584a7c177` |
| 普通系统 `a4c727bdbd27cbd2` manifest | `bbbbca009bd9859cce7e22b3402345927dccb1580524efd37f0c4fd3eb2f0360` |
| `build/ordinary-bridge-guest-final/report.json` | `b25df4f56402c70abd7db70b0fe4c53577e2e3fa269c6487863036ab6a9f522e` |
| `build/ordinary-bridge-guest-final/guest_serial.log` | `2671abfb54ef1db22473718a459699f58726b30604f08d6b0f49b625a0572c17` |

## 配置边界

两次读取重建各自启动内的封存对象，由恢复出的同一持久账户拥有；跨启动保留的是
账户身份与吊销状态。物理独立代际、可信物理用户输入和命名文件的持久归属仍待专项
验收。 [资源服务授权](../contracts/pumpkin_resource_service.md)
