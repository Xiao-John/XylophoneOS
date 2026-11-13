# IP4 bulk、设备授权后端与用户态 VirtIO 网络纵切

编号：`07374f76`，由 `scripts/work_log_id.py` 按本标题生成。日期：2026-11-12。

## 授权、基线与资格

基线为 `158a9b99550c03b97e74e3b9e4c2fd6a288c8bf3`，分支为
`codex/ipc-device-runtime-20261112`。实现期间上游合入 PR #112，已合并
`ddcbefa95bfbe0b56f02118dfa2055fe8043b6be`，采用其公开 IP4 ABI 和后端。
本轮用户明确要求继续完成此前待办和规划，允许
在没有 guest 环境时提交已经实现但未验收的功能。因此 **可调用能力与验证资格分开**：
sys88 query 返回 `0x1f`，bulk 已能调用；manifest 的 bulk `guest_qualification=not_run`。
sys112 的 11 个操作有实际后端，状态为 `implemented_unverified`，guest 同样未运行。
IP2/IP3 既有记录保留原范围，IP5 性能、旧报告和旧发行资产不因本轮修改获得新资格。

没有修改 `docs/state.md`、`docs/tech_debt.md`、工作日志索引或旧冻结报告。
此次实现不另占 syscall 号：沿用 sys88 actions 19–23、已登记的 sys112 operations 1–11；
sys89 留给并行 CPU accounting 工作。

## 实际完成

### IPC bulk：采用新合入上游 ABI

本轮开发期间上游 PR #112 合入。未提交的另一套 bulk 草案及其测试已移除，最终只有
上游 [共享 ABI](../../src/shared/include/xos/ipc_v1_abi.hpp)、
[任务后端](../../src/kernel/arch/x86_64/tasks.cpp) 和 [SDK](../../src/user/include/xos/ipc_v1.hpp)
的 grant_create/delegate/map/unmap/close（19–23），不登记第二套动作或结构。
create/map 为 72 字节、unmap 为 48 字节；delegate 向目标安装与源句柄相同的值，
查找同时匹配 value/holder，目标已有同值时返回 resources。

沿用内核新分配并持有引用的页、source 快照或清零、只读/读写 NX 映射、精确匿名 VM
reservation、pin 检查、引用回收与失败回滚。每对象最多 64 页，系统 16 grants /
64 mappings，所有 IPC handle 共用每进程 8 个额度。manage close 发现 pin 时无副作用
返回 busy；退出/成功 exec 撤销该 holder 的映射和 handle，最后一个 handle 清理后销毁。
没有独立 bulk 窗口、租约或动作 24。当前修改只开放可调用 feature 位、保留旧 SDK
query 兼容。device 映射的 fork 拒绝在本分支实现，grant 映射的同类拒绝由根分支的
VM/COW 集成提交处理，避免私有快照遗失共享对象记录。

上游 [guest fixture](../../tests/fixtures/ipc_v1_grant/ipc_v1_grant_probe.cpp) 和
[runner](../../tests/ipc_v1_grant_guest.py) 保持同值 delegate 断言，当前可调用 feature
断言更新为 0x1f。PR #112 的 3 轮历史 guest 和资源守恒仍只覆盖其原构建；本轮未运行。
完整字段、错误与配额见 [IPC 契约](../contracts/ipc_v1.md)。

### 设备授权

[device store](../../src/kernel/core/device_grants.hpp) 实现 grant/owner/不可回绕 token、
资源 query、MMIO map/unmap、连续 DMA allocate/release、IRQ bind/wait/ack、revoke/close。
[sys112 接入](../../src/kernel/arch/x86_64/device_tasks.inc) 一次快照、精确验证子结构、
副作用前验证并 pin 输出。无输出的 unmap/revoke/close 不回写请求；DMA_ALLOC 失败级联
撤销了自身输出地址时返回 FAULT，不对已经失效的窗口 copyout。

授权来自真实 bootstrap supervisor 对其 owned building child 的受保护关系，不使用
程序名、路径或进程自报 PID。当前设备 profile 是未启用 bus mastering 的 network-class
PCI type-0 function；显示和存储继续归原内核路径。有限 QUERY 返回该设备 BAR 长度、
独占 IRQ 和清除了 BAR/ROM/MSI 地址的只读配置快照，不开放 PCI I/O 或任意 config 写。

MMIO 使用 user/NX/UC 页表，窗口 `0x210000000000..0x210010000000`，每进程 16 个
16 MiB slot，系统 128 映射。系统最多 16 grants；每 grant 最多 1024 DMA 页，每 owner
2048 页，系统 4096 页，均计入 quarantine；单次最多 4 MiB，使用真实连续物理 allocator。
IRQ 通过已有 PIC 后端和实际 ISR 路由；到达后遮罩、记录序号、唤醒 WAIT，由用户态清
设备原因后 ACK，精确匹配序号才解除遮罩，重复 ACK 不伪成功。

退出、fault、exec、显式 close/revoke 都先撤 CPU 映射、同步页表并取消等待，再处理 DMA
停止与页回收。当前只为 `1af4:1041` 和含现代 common capability 的 `1af4:1000` 提供
DMA 回收证明：**用户态执行 reset，内核只读观察 device_status=0，并禁用/读回 BME**。
依据 [VirtIO 1.2 §2.4.1、§2.4.2](https://docs.oasis-open.org/virtio/virtio/v1.2/virtio-v1.2.html)，
reset 完成后设备不能继续访问队列。没有把 PCIe Transactions Pending 清零当成
posted-write 普适排空证据；其他设备 DMA 请求明确拒绝。

未完成复位的 kill/fault 或无法确认停止的路径返回 UNKNOWN，并保留 DMA 页和设备
instance，不能重新分配给其他 owner。只读 reset observer 最多 16 个，保留的有界
内核映射不计作用户 DMA 泄漏。**未实现 IOMMU；授权的驱动和设备必须受信**。
MMIO/handle 鉴权和 DMA 页配额不限制恶意驱动填写任意设备地址；quarantine 处理停止
证据不足时的页回收，不提供硬件 DMA 隔离。详见 [设备契约](../contracts/device_authorization_v1.md)。

### 用户态网络纵切

[真实驱动](../../src/user/drivers/virtio_net.cpp) 实现现代 PCI capability transport，
协商 VERSION_1/MAC，建立 RX0/TX1 两个 64-entry split ring。66 页连续 DMA 承载
descriptor/avail/used 和 2048 字节槽，现代网络头 12 字节，帧上限 1514 字节。
TX 满不覆盖设备持有的槽，消费真实 used ring、检查返回 ID/长度、处理 16 位 index 回绕，
IRQ 使用 sys112 wait/ack，reset 和报文处理在用户态。

[net_service](../../src/user/programs/net_service.cpp) 发布有限 raw Ethernet 协议，
提供 MAC 查询、发送、接收和受 controller PID 认证的 stop；同时一个会话、最多缓存
8 帧，满时丢最旧帧。supervisor 的 `net-start <instance>` 通过既有受控 channel 交付
grant，`net-stop` 验证服务 peer PID；重复 start 不覆盖仍在运行的服务身份。
`net-probe <instance>` 发 ARP、检查网关回复和 IRQ，正常停止先 reset 再关闭 grant。

构建源头新增 net_service 和真实驱动对象，普通/线程 SDK 同步发布设备能力及资格；
未手改任何生成头或发行物。QEMU 的 `--network` 显式启用现代 VirtIO-net，BDF 00:05.0
即 instance=41，禁用 NIC ROM；默认无网络 profile 保持原值。没有新增 host 端口转发。
协议、profile 和运行命令见 [网络纵切契约](../contracts/net_user_driver.md)。

## 实际验证与可重放命令

在仓库根运行：

```sh
python3 tests/ipc_device_host.py
python3 tests/virtio_net_host.py
python3 tests/ipc_v1_query_compat_test.py
python3 tests/ipc_v1_reference_model.py
python3 tests/docs_consistency.py
python3 tests/abi_doc_consistency.py --output-dir build/ipc_device_host
```

| 检查 | 本轮结果 | 证据边界 |
|---|---|---|
| ipc_device_host | 8 场景通过 | 真实 device store 和 allocator；Linux shared mmap 替代页表，PCI/PIC 回调是硬件边界替身 |
| virtio_net_host | 5 场景通过 | 编译真实 capability parser/split queue；含 65,540 次 index 回绕，不执行 syscall/PCI/IRQ |
| ipc_v1_query_compat_test | 9 场景通过 | 旧/新 SDK 对真实 query 分支，正常 supported=0x1f；计数仍显式 opt-in |
| ipc_v1_reference_model | 19 测试通过 | IP2/IP3 模型及两个 SDK manifest 接入检查，不能代替运行时或 bulk 客体 |
| docs_consistency / abi_doc_consistency | 通过 | 相对链接、登记及源码接口一致性 |
| 受影响 C++ 单元严格对象编译 | 11 个通过，另 3 个 VM/COW 变体通过 | 宿主 GCC 14.2.0，仓库 COMMON_FLAGS/X86_FLAGS，含 -Werror/-Wconversion/-Wshadow |
| Python 入口语法、git diff --check | 通过 | 修改及新增脚本可解析、补丁格式 |
| QEMU 命令构造 | 通过 | 检查默认/网络 profile、ISO、单核参数；只构造命令，未启动 QEMU |

11 个对象包括 tasks/paging/exceptions/memory/PCI/PIC、真实网卡驱动、net_service、
supervisor、上游 IP4 guest fixture 和 device ABI fixture。tasks 编译仅提供 user_images /
user_blobs 的声明及 build_info 常量，没有生成真实内嵌镜像或链接内核。
另编译 tasks 的 VM1 / VM1+COW1、paging 的 COW1。上游 IP4 fixture 首次误用普通
newlib 头的检查失败；改用项目 threading 头、原 runner 的宏和系统化第三方头后通过，
这是验证配置纠正，不记为目标代码缺陷或 guest 资格。
临时命令、返回码和输出在 `build/ipc_device_host/validation.json`；该本地日志是可重跑
检查记录，不是冻结客体资格。宿主 fixture 有直接引用生产源码，不复制授权或队列业务实现。

具备仓库固定工具链、NASM、QEMU 和同源系统产物后可执行：

```sh
python3 scripts/build.py --output-dir build/ipc_device_system
python3 tests/virtio_net_guest.py --system build/ipc_device_system
```

网络 runner 校验 system manifest 的全部源码/产物散列并记录原始串口。
上游 IP4 runner 另需同源 threading SDK（含 C++ 库），使用其现有
`--system`、`--sdk`、`--output` 参数；旧 device_abi_guest 也需要该 SDK，不可用普通 SDK
替代。两项均未在本轮运行。
网络 runner 要求三轮真实 ARP 往返、IRQ、close=0，以及首轮有界 observer 分配后的
稳定资源基线。本轮 **NASM、固定 x86_64-elf 工具链和 QEMU 均缺失**；汇编、完整链接、
guest、ARP、MMIO 页表隔离、真实 IRQ/DMA 时序与性能全部 NOT_RUN，不能从上述宿主
通过推导为客体通过。没有覆盖完整设备负向并发套件，也没有改旧验收数据。

## 尚未完成及集成要点

- 网络只提供 raw Ethernet，没有 TCP/IP socket、DNS、TLS、HTTP、DHCP、路由或浏览器联网。
- 不支持 generic 设备安全回收、共享 IRQ、热插拔、SMP 或 IOMMU；不承诺任意驱动死亡
  都能归还 DMA。显示、输入和存储迁移仍按原契约另线推进。
- 与并行 VM/COW 工作集成时，bulk 使用现有匿名 arena，device 保留独立 33 TiB 窗口；
  共享/DMA/MMIO 的硬件可写 PTE 不应仅因引用数大于 1 自动私有化。fork 拒绝持有
  映射的组合路径由根分支核对；撤销在地址空间销毁前。
- VM 的原子 copyout wrapper 集成 sys88/sys112 时保留错误域与 pin 行为；没有输出的
  撤销操作不写回失效请求，阻塞 IRQ 输出在进入等待前已 pin。
- SDK 生成器合并时保留另一分支的 archive provenance/build-id 字段和本轮
  device_authorization、ipc_v1 guest_qualification 字段，不用一方覆盖另一方。

实现、网络纵切和 SDK 构建发布仅本地分阶段提交；没有 push 或把这些变更合入远端主线。
