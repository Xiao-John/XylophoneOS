# 60325ea6 · Pumpkin daemon native IPC

2026-11-26 · P1 在 `6c68e052` 的核心上接入已有 sys84–86 和 sys46/47、sys63。
[私有协议和启动契约](../contracts/pumpkin_daemon_p1.md) 对应单独测试 profile，普通
端点与父进程持有的登记端点彼此隔离。凭据留在 IPC 和用户态工作缓冲。已送出请求缺
有效回复时客户端报告结果未知。首次编译缺少线程 ABI 的直接引用，修正后编译成功。
带调试节的探针超出构建尺寸检查，按原生探针惯例移除调试节后链接与装载均通过。

## 验证

工具为 Apple Clang 21.0.0、x86_64-elf GCC 16.2.0、Python 3.12.15、QEMU 11.1.2。
宿主正常和 ASan/UBSan 各八组通过，含协议非法字段、重放、失效期限、回包数据和序号校验。
x86-64 对象编译、现有 ABI 一致性及完整 ELF 静态链接通过。

```sh
python3 tests/pumpkin_host.py --target-cxx x86_64-elf-g++ --output build/pumpkin_p1/host
python3 tests/pumpkin_host.py --sanitize --output build/pumpkin_p1/sanitized
python3 scripts/build_pumpkin_daemon.py --sdk "${XOS_SYSTEM_DIR}/sdk" --output build/pumpkin_p1/native_r3
python3 scripts/build_dash.py --sdk "${XOS_SYSTEM_DIR}/sdk" --archive "${XOS_DASH_ARCHIVE}" --receipt build/pumpkin_p1/dash.json
python3 tests/pumpkin_daemon_guest.py --system "${XOS_SYSTEM_DIR}" --fixture build/pumpkin_p1/native_r3 --dash-receipt build/pumpkin_p1/dash.json --output build/pumpkin_p1/guest_dual
```

客体取 `9f7a9a0f` 捕获的系统和 SDK。runner 重验系统源码、ISO、SDK 和被测程序。
dash 来自源码锁固定的 0.5.13.5 源归档，用同套 SDK 新构建。xsh 直接运行
`/bin/pumpkin_probe.elf`，dash 运行 `/bin/dash /bin/pumpkin.sh` 后启动同一探针。
两条入口均在真实 QEMU 中完成账户创建、错误与正确认证、普通端点管理操作拒绝、
跨连接会话拒绝、注销、轮换与吊销、请求发送后断连的结果未知、重启生成新空库。
两次 shell 入口结束后的空闲页数、任务数、完成记录数均等于基线 `129700 / 3 / 1`。
两个连接拒绝用例由同一探针进程发起，独立进程互访和实际存储故障尚待测试。

| 绑定工件 | SHA-256 |
| --- | --- |
| 系统 `3c8ccf57d6041f7c` manifest | `8ac79af845c72d0e2bd7f512f08286d5d612c5d9b50cfd52a7657ec823c6bc2f` |
| 系统安装 ISO | `dd6e18958a6c543160a3b7823f320d7b8ace72e96c9dcbc50f72a004ea90332e` |
| SDK 树 | `1a64f84ce78fcfd99e37aaba78cad7c131eab8bb2fd31b76b449c28f2063710c` |
| `pumpkind.elf` | `627af9c6f43c9e4dfe2cb4b3663c7bdffd438438ac526b21f5a9d632a0de7569` |
| `pumpkin_probe.elf` | `04ff6d2245049eb102d65f613570b8123e0235ac25be7385ea9b6dadaa626634` |
| dash | `94be9cc12698f6da03be0737e938f0c3d1f42061c3f89f3bcec869fcfc191067` |
| `build/pumpkin_p1/guest_dual/report.json` | `9dfbd5dac8d8db5a6a54af31dd62ed29bf51eb33496904f7afa0f3d20a57396c` |
| `build/pumpkin_p1/guest_dual/guest_serial.log` | `ae85d9161e089fda1c225e4de672f136b4c05f80d7e555402b92bf72c065e4ae` |

## 交接

测试账户库只保存在守护进程内，重启会主动创建新安装域。真实文件系统后端仍缺私有
对象授权、原子持久发布以及防回滚保证。公开消息和 SDK、正式启动器与登录客户端、
故障捕获保密、实际文件所有权和 Mobius 客体验收待后续。当前完成度为 `passed_subset`。
