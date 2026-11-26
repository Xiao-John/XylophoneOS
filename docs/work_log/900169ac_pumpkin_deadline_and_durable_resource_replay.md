# 900169ac · Pumpkin deadline and durable resource replay

2026-11-26。以已复验的 broker 到期修复叠加原持久资源候选。组合源码的构建输入
与公开提交 `0a733bd55d774b15de2b3988597b8d7d15f78793` 一致。两份树仅有前序
到期工作日志的文字差异。本次按组合源码重建所有实际运行镜像。
[到期修复](32dbebc0_pumpkin_broker_deadline_separation.md)
· [原持久持有者](7ce64487_pumpkin_durable_account_resource_login.md)

组合的客户端处理保留实际接收时间复核与独立服务间回复期限。已到期的普通调用
丢弃结果，broker 消费有效服务回复后可继续接纳下一次读取。持久登录的同一持有者
在成功读取后准备下一次关联，登出并在其两秒有效期内确认拒绝。

## 验证命令

```sh
python3 -B scripts/build.py --pumpkin-anchored-probe --pumpkin-native-login \
  --pumpkin-user-login --pumpkin-user-resource --output-dir build/resource-system
python3 -B tests/pumpkin_user_login_guest.py --resource --system build/resource-system \
  --output build/resource-guest
python3 -B scripts/build.py --pumpkin-anchored-probe --pumpkin-native-login \
  --pumpkin-user-login --output-dir build/login-only
python3 -B tests/pumpkin_user_login_guest.py --system build/login-only --output build/login-only-guest
python3 -B scripts/build.py --output-dir build/ordinary-system
python3 -B scripts/build_pumpkin_daemon.py --bridge-probe --sdk build/ordinary-system/sdk \
  --output build/ordinary-fixture
python3 -B scripts/build_dash.py --sdk build/ordinary-system/sdk --receipt build/ordinary-dash.json
python3 -B tests/pumpkin_daemon_guest.py --bridge-probe --system build/ordinary-system \
  --fixture build/ordinary-fixture --dash-receipt build/ordinary-dash.json --output build/ordinary-guest
python3 -B tests/pumpkin_daemon_loop_host.py --sanitize
python3 -B tests/pumpkin_host.py --sanitize --target-cxx x86_64-elf-g++ --output build/host-core
```

QEMU 11.1.2 使用同一已登记凭据在两个新 VM 执行真实资源读取并登出。两次都在
待用关联的两秒期限内获得拒绝，且读与登出前后的盘外标记一致。实际吊销发布后，
新 VM 用该凭据请求读取返回退出码 3。组合资源镜像通过 16 项，独立原登录镜像通过
13 项。普通镜像的 xsh 和 dash 各通过 13 项 broker 检查，均恢复
`[129711, 3, 1]`。受控时钟中共享通道排空及复用的回归、ASan/UBSan、目标编译和
许可材料审计通过。三份系统清单的源文件与 ISO 摘要已对照组合树重新核验。

| 工件 | SHA-256 |
| --- | --- |
| 资源系统 `207736e0d17dca7f` 清单 | `fdcbb1972dcc5304040d8821543b05801472b28079a3c421bd133aba2e038b91` |
| 资源系统 ISO | `baebefa29d51419b0fd2ace41d790b28dcf9b33ea9d2411034383d002ce8fb8c` |
| `build/resource-guest/report.json` | `871167ce8fe65be5ab9cff7b24b7e7dad976b1bef67d9c476698aba34c56712d` |
| 登录系统 `80391d164d8229b7` 清单 | `8c3ecf99767eb4c66caf2288bd576f483ef6e9cdc132a03134769c9465fbe2b4` |
| `build/login-only-guest/report.json` | `f67718dabef37676b5c96e9dbc723f810023b696321a770fb1ba4b451412e9bd` |
| 普通系统 `1b5269d995185f78` 清单 | `3020ae5221e97dae0837ef0537734f16265bc2bd4c79c364b82b504b7623f649` |
| `build/ordinary-guest/report.json` | `1563e32ccea546c995ab3e980093cad2be792810f943c61b31cf026aff88e09d` |
| `build/ordinary-guest/guest_serial.log` | `a6b6c86f67c18e223764832ce4d26937ef6515422436a239edf3531292b9ed22` |
