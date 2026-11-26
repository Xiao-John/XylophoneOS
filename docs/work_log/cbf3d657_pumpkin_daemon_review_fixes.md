# cbf3d657 · Pumpkin daemon review fixes

2026-11-26 · 复核 PR #183 的三项意见。构建器增加两个传递 ABI 头的源码比对。
守护进程先读取回复槽状态，只有槽仍占用且预算已用完才按回复超时断开。回复预算
从成功入队后的时钟采样起算，覆盖较慢的请求处理。

```sh
python3 tests/pumpkin_daemon_loop_host.py
python3 tests/pumpkin_daemon_loop_host.py --sanitize
python3 scripts/build_pumpkin_daemon.py --sdk "${XOS_SYSTEM_DIR}/sdk" --output build/pumpkin_review/native
python3 scripts/build_dash.py --sdk "${XOS_SYSTEM_DIR}/sdk" --archive "${XOS_DASH_ARCHIVE}" --receipt build/pumpkin_review/dash.json
python3 tests/pumpkin_daemon_guest.py --system "${XOS_SYSTEM_DIR}" --fixture build/pumpkin_review/native --dash-receipt build/pumpkin_review/dash.json --output build/pumpkin_review/guest
```

宿主正常和 ASan/UBSan 各通过两个回归场景。变更临时 SDK 中的 `file_abi.hpp` 或
`spawn.hpp` 均使构建器在生成工件前明确拒绝。实际 xsh 和 dash 在绑定系统
`3c8ccf57d6041f7c` 上退出码为零，资源回到原基线 `129700 / 3 / 1`。
现有 ABI 一致性检查通过。

| 工件 | SHA-256 |
| --- | --- |
| 绑定 SDK 树 | `1a64f84ce78fcfd99e37aaba78cad7c131eab8bb2fd31b76b449c28f2063710c` |
| `pumpkind.elf` | `fedac8228f6c7929cd9b7c0898e44db9242172168ca7a1811a42596cdde14847` |
| `build/pumpkin_review/guest/report.json` | `fae0c82945a01b6f6437e9fe9912b05f51ca4c0dc17492cd5457a51c895683ee` |
| `build/pumpkin_review/guest/guest_serial.log` | `312081da1ba82fcc46dc3c3b403ec7a348f5159953527cb809fdbfcac49d6e7b` |

测试领域为 P1 易失守护进程。实际持久存储、正式安装和资源服务接入仍待验证。
