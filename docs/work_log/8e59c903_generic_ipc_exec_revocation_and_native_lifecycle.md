# Generic IPC exec revocation and native lifecycle qualification

2026-11-25。本模块叠在 PR #155 的网络会话/TCP 加固后，修复 N2 生命周期客体
发现的内核缺口：成功 exec 保留 PID，却保留了旧映像的 sys84–86 通用端点和
发布名称。替换后的程序可以继续看到未声明继承的通信权利，服务也不能及时回收
旧连接。机制边界见 [IPC endpoint 生命周期](../contracts/ipc_endpoint_lifecycle.md)。

## 修改与边界

`revoke_generic_ipc_process` 统一撤销名称、待 accept 的连接、pair 两端及待消费
消息，并唤醒阻塞对端。进程销毁与成功 exec 共同使用此实现。exec 撤销点位于
entry、authority、文件会话和显式 channel 继承的全部可失败检查之后。
失败 exec 完整保留原映像的名称、端点及消息。

没有新增 syscall、结构或错误码；sys81 显式静止 channel 继承、sys88 IPC v1
及 files 专用会话继续沿用各自契约。公共 process ABI 头、登记和专项文档同步
说明成功替换的撤销语义。通用 Guest 增加可选 serial-only 模式，默认 QMP 行为
保留；本环境无法创建 AF_UNIX QMP socket，串口足以观察本模块全部结果。

## 实际验证

使用 `xos-glibc-sdk-preview` 的 GCC 16.2.0、Binutils 2.47.20260726、
QEMU 11.1.3，x86-64 TCG、单 CPU、512 MiB、新 FAT32 测试盘。
native fixture 不链接 libc，实际执行 child spawn、一次失败 commit 和一次成功
exec。每轮生成新的 32 字节 nonce，IPC 双端查询内核认证 PID。

**真实客体 3 轮全部通过**，每轮均观察：

- 失败 exec 保留原双向通信；parent 连接原名称成功，过程中没有重新发布名称。
- parent 建立未 accept 连接并投递私有消息；成功 exec 后两端、消息和待接连接
  被撤销；阻塞的 parent 被唤醒。
- 新映像对旧名称执行 unpublish 得到 denied，随后重新发布成功；对旧句柄的
  send/receive/query_peer 全部失败。
- 相同 PID 使用全新的端点 token 重连，通过双方身份和 nonce 校验。
- child 正常退出，资源每轮精确回到 **129720 free pages / 3 tasks / 1 completion**。

既有 `kernel_process_wait_race_test.py` 的正常/故障退出、孤儿回收、构造取消、
kill 传播、等待唯一消费、pending waiter 和跨页 pin 检查通过。

最终 build ID：`79e9f31e75f572f5`。

| 原件 | SHA-256 |
|---|---|
| `build/ipc_exec_system_v3/xos-install.iso` | `f9818abf2a1afaaa51f088ec929290fc4683a41603684c8f62fde6b4ace195ea` |
| `build/ipc_exec_system_v3/manifest.json` | `e5320994f1699b8793fcb8adec0ac69122c320b903767ba8a51dbff4ba220f4c` |
| `build/ipc_exec_fixture_v3/receipt.json` | `5dc454a4236c5e9e434bc52ceb5576735307a70832b9ceb3eb4dbe30532179a3` |
| `build/ipc_exec_fixture_v3/ipc_exec_probe.elf` | `4125e87b4b291114d6479a35f40108fcc89d8f4920f545ee6c33d5efb2879d1b` |
| `build/ipc_exec_guest_v3/report.json` | `534a427249a6d247562a7c8296a1a605e67913b390b938bda73e2e986f9214c7` |

公开证据见 [manifest](../reports/ipc_exec_20261125/manifest.json)。guest_report
是移除宿主路径的派生摘要，保留原报告 SHA-256；两份日志为原字节。索引核对
公开文件的实际散列，源码/SDK/系统/fixture 在验收前后逐项验证。

初次 harness 使用 128 MiB FAT32，被创建器支持的 512..2048 MiB 范围正确拒绝，
客体尚未启动。第二次 fixture 把同 owner 发布名称误判为 busy；内核现有语义是
幂等成功。最终探针用 peer 连接证明失败 exec 保留名称，并用 denied unpublish
证明成功 exec 移除名称，避免重新发布操作掩盖生命周期缺陷。旧失败报告保留。

## 复现与交接

`XOS_SDK_RUN` 为已核对的 preview 工具入口；输出使用新目录。

```sh
"$XOS_SDK_RUN" python3 scripts/build.py --output-dir build/ipc_exec_system
"$XOS_SDK_RUN" python3 scripts/build_ipc_exec_probe.py \
  --sdk build/ipc_exec_system/sdk --output build/ipc_exec_fixture
"$XOS_SDK_RUN" python3 tests/ipc_exec_guest.py \
  --system build/ipc_exec_system --fixture build/ipc_exec_fixture \
  --output build/ipc_exec_guest --serial-only --repeat 3
python3 tests/kernel_process_wait_race_test.py
python3 scripts/verify_evidence_index.py docs/reports/ipc_exec_20261125/manifest.json
```

sys81 继承压力、完整终端/显示/Interactium、SMP 和真实硬件尚未在本模块重跑。
网络模块将组合本修复重新构建镜像，完成 exec、撤销、超时、fault、service restart
及多应用资源回收验收；glibc 出站 exec 也应使用该明确撤销边界。
