# 4368aa56 P1-E 应用 authority 与持久发布事务

基线：`24b57a268681fae38dff5836c8b9cf0837685ae3`。本组完成 P1-E 的有界
逐应用数据 authority 与应用数据/安装元数据可恢复事务，并给 P1-C/D 提供同一
发布单元中的 catalog/checkpoint 接口。P1-C 的动态启动绑定与跨真实后代即时
检查另行交付；本组两个客户端连接的撤销证据不冒充后代进程证据。

## 实现与边界

- 新 `provisioning_store` 使用既有 `snapshot_publication`/`anchored_files_store`，
  完整保留 64 账户容量，增加 8 个应用记录、每应用 512 字节状态和安装 receipt。
  所有账户、应用授权、数据、安装 receipt、catalog/checkpoint 共用一次 CAS。
- 显式 private region/lease v2 的两个 16 KiB 槽；旧 9-sector v1 profile 不变。
  未知提交结果停服务并有界排空最终回复，不自动重放。
- 普通 RPC 使用真实连接账户 session 加独立应用凭据；owner 来自受保护记录。
  跨应用凭据、伪造 owner、旧授权 epoch、普通客户端发布 catalog 均拒绝。
- 服务端登记的限权 catalog publisher 需要真实 registrar 和 kernel 验证的
  daemon-side endpoint pair/peer；该角色没有账户、应用或再次委派权限。
- 客户端实现从 `native_ipc.cpp` 拆为 `native_ipc_client.cpp`，供独立发行控制器
  复用；没有复制一套较弱协议。普通账户协议继续共享原有 sequence/deadline。

接口、边界与失败语义详见
[`pumpkin_application_persistence.md`](../contracts/pumpkin_application_persistence.md)。
主要实现为 `src/user/pumpkin/provisioning_*`，相关存储/profile 接线在
`files_private_storage.hpp`、`files_private_lease.hpp`、`files_slot_client.cpp`、
`scripts/build.py`、`scripts/user_build.py` 和独立 generation authority。

## 实际验证

所有构建与验收均在固定 glibc preview-3 SDK 开发环境中执行，构建使用项目
的隔离输出目录。可复现命令（相对源码根，SDK launcher 提供工具）：

```sh
python3 tests/pumpkin_provisioning_host.py --output build/p1_ce_host
ASAN_OPTIONS=detect_leaks=0 python3 tests/pumpkin_provisioning_host.py --output build/p1_ce_host --sanitize
python3 tests/pumpkin_host.py --output build/p1_ce_legacy_host
python3 tests/pumpkin_daemon_loop_host.py
python3 tests/pumpkin_generation_authority_host.py
python3 scripts/build.py --output-dir build/p1_ce_guest --pumpkin-anchored-probe --pumpkin-provisioning-store
XOS_QMP_TRANSPORT=pipe python3 tests/pumpkin_provisioning_guest.py --system-build build/p1_ce_guest --output build/p1_ce_guest_report_pipe
```

全部通过。Host 直接编译生产 codec/store/RPC，验证 torn stage、明确拒绝 CAS、
committed/uncommitted unknown、精确恢复、旧磁盘拒绝、跨应用拒绝、持久撤销、
publisher 限权、防回退 checkpoint 和满 64 账户。既有账户、named resource、
daemon/broker lifetime、独立 authority 9 项回归均通过。

Guest 使用 QEMU 11.1.3，14 次新 VM 启动覆盖四组事务结果：

| 注入或提交结果 | 冷启动选中 revision | 应用数据与安装 receipt |
| --- | --- | --- |
| committed | 8 | 完整新状态 |
| rejected CAS | 7 | 完整旧状态 |
| committed 后 outcome_unknown | 8 | 完整新状态，旧 daemon 停止 |
| 未 committed 的 outcome_unknown | 7 | 完整旧状态，旧 daemon 停止 |

两组已发布新根的旧磁盘快照均被拒绝。每次初始化都通过真实 Files 私有租约
与 Pumpkin IPC 检查跨应用拒绝、普通 catalog 发布拒绝及两个已建立连接的
撤销失效，后续新 VM 检查撤销仍持久。

构建 ID 为 `9c844c127b07c6e4`，system manifest SHA-256 为
`0028fb21d136cd9c90b7d6d8dc6f884546ff06da999e8aaa6bc6baac15d900ce`。
完整产物 receipt 与每次启动的 CAS/ACK 事件见
[`p1e_application_persistence/report.json`](../reports/p1e_application_persistence/report.json)，
平铺根清单为
[`p1e_application_persistence/manifest.json`](../reports/p1e_application_persistence/manifest.json)。

初次 sanitizer 默认 LeakSanitizer 在 SDK 的 ptrace 执行方式下无法运行；显式
关闭 leak detector 后 ASan/UBSan 实际通过，不声称做了 leak 检测。首次 QEMU
默认 Unix QMP socket 被执行环境禁止，改用既有 pipe transport 后全部通过。
构建还修复了非 native-login anchored profile 缺失 session_limits include 的
真实编译错误。

## 未声称与下一步

这是有界应用状态服务，不是任意大小的 POSIX 文件事务。Guest 的故障注入
针对真实写入之后的 authority CAS/ACK 边界；host 的 torn write 模型是单独
证据，不冒充 guest 的任意扇区掉电。本组未做真实磁盘控制器、任意物理断电、
整机/authority 同时回滚资格，也没有宣称全局瞬时停止正在运行的代码。

下一步 P1-C 以显式 startup capsule ABI v3 将可信 catalog 服务绑定传播到
动态后代，在每次 admission 查询当前撤销状态；P1-D 完整验证签名、包闭包和
对象后，通过限权 publisher 使用本组原子 catalog/checkpoint CAS。全局状态
由集成者在各 PR 合入时更新。
