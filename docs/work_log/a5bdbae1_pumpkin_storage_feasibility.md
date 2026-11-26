# a5bdbae1 · Pumpkin storage feasibility

2026-11-26 · 基线为 `9f7a9a0f` 文件服务与 Pumpkin P1 `c53b1057`。
[持久化勘查](../contracts/pumpkin_storage_feasibility.md) 核对 files 单文件替换、
设备同步和 xypm P2 维护 journal。试验只写专用 FAT32 临时工作盘，快照占 4432 字节，
包含 64 个纯测试吊销记录与校验摘要，全程没有登录凭据或生产数据。

## 实际运行

工具为 QEMU 11.1.2、Python 3.12.15 和 x86_64-elf GCC 16.2.0。同一 SDK 的 dash
0.5.13.5 沿用本分支 P1 新建的带输入回执工件。runner 在运行前后核对系统源码与 ISO、
SDK 树、dash、探针源码及工件哈希。进程资源在每个步骤后回到各启动基线
`129700 / 3 / 1`。

```sh
python3 scripts/build_pumpkin_daemon.py --storage-probe --sdk "${XOS_SYSTEM_DIR}/sdk" --output build/pumpkin_storage/native
python3 tests/pumpkin_storage_guest.py --system "${XOS_SYSTEM_DIR}" --fixture build/pumpkin_storage/native --dash-receipt build/pumpkin_p1/dash.json --output build/pumpkin_storage/guest_final
```

| 启动 | 实际行为 |
| --- | --- |
| 1 | xsh 普通进程直接块查询被拒，维护写租约被拒，files 写入与同步版本 65 成功。dash 启动另一进程，暂存并同步版本 66 的首个扇区，在提交之前以 70 退出。xsh 再开普通会话读回完整版本 65。 |
| 2 | 宿主关闭并重新启动 QEMU。dash 读回完整版本 65。不同的 xsh 普通进程通过 files 读取并替换成版本 66。 |
| 3 | 再次重新启动后，xsh 和 dash 都读回并校验版本 66。 |

这组证据确认同步后存留与已确认提交前的进程失败。普通独立会话有读写权，候选
FAT 路径未取得私有后端资格。真实后端、断电、提交操作内中断、扇区撕裂与版本锚点
均未运行。默认构建入口复验通过，P1 测试守护进程用同一 SDK 在 xsh 和 dash 再通过。
现有 ABI 一致性通过。

| 工件 | SHA-256 |
| --- | --- |
| 系统 `3c8ccf57d6041f7c` manifest | `8ac79af845c72d0e2bd7f512f08286d5d612c5d9b50cfd52a7657ec823c6bc2f` |
| 系统安装 ISO | `dd6e18958a6c543160a3b7823f320d7b8ace72e96c9dcbc50f72a004ea90332e` |
| SDK 树 | `1a64f84ce78fcfd99e37aaba78cad7c131eab8bb2fd31b76b449c28f2063710c` |
| `pumpkin_storage_probe.elf` | `b2dfd01770acfd26c03ecfd378ade997fa0b72ff52d10ba8fc8a953ac3d5ff39` |
| dash | `94be9cc12698f6da03be0737e938f0c3d1f42061c3f89f3bcec869fcfc191067` |
| `build/pumpkin_storage/guest_final/report.json` | `9418f1830c98f00ddf2ff22663d26eb697bdf087ad07c9cbbc0dcd07a33dff23` |
| `build/pumpkin_storage/guest_final/boot1_serial.log` | `82ad82fe6dd982831fce37d992c34c85e823856e6d65e108885b134ca51c39b7` |
| `build/pumpkin_storage/guest_final/boot2_serial.log` | `c2924222971adeadd46c278028c1efdac319e92b4c9fb7d94ff239d94a19ee36` |
| `build/pumpkin_storage/guest_final/boot3_serial.log` | `43982b839afae3724d708d5f84b55201ee16ffa44fcd6f48afd3007c6cd2a698` |

## 交接

先验证受信启动者向 Pumpkin 授予并重建持久私有对象的能力，再从可证明的比较替换、
同步和防回滚边界接入生产账户库。继续保持现有内存测试配置以独立验收 IPC。
