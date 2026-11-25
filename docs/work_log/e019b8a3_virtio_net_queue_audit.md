# VirtIO-net 队列所有权与故障处理审计

2026-11-25。基线 `08f3e13ead01c0d8d7d535e9f85d7d94510c2b20`；独立分支
`codex/net-driver-audit-20261125`。范围是用户态 VirtIO-net split queue、对应宿主
夹具和测试入口，不修改 syscall、设备授权、服务协议、glibc 或其他运行库。

## 发现与修复

1. **同批 RX 完成记录重复引用同一 descriptor。** 原代码的 `active_` 对 RX 始终
   为真；处理第一条记录后立即重新发布 descriptor，已经在 used ring 中的第二条
   重复记录也会通过。现在先快照本次新增的全部完成记录，逐项验证所有权、ID 和
   长度，转为待交付状态，再允许回收和重新发布。待交付 descriptor 收到重复完成
   同样返回 `device_io`。已验证元数据保存在有界私有数组中，不二次读取 DMA 元数据。
2. **复用已停止队列的页时继承旧 flags/index。** `initialize` 原先只清理本地计数器，
   留下共享 avail/used 控制字段。现在在设备已 reset、队列尚未启用的前提下清零
   4 KiB 控制区，并重新建立 descriptor 和 available ring。该函数仍要求有效的
   backing pages；调用它本身不会停止活动设备。
3. **故障后继续使用损坏队列。** 越界 ID、重复完成、错误长度/头、used index 异常
   现在锁存失败状态。后续收发继续返回 `device_io`，只有完成设备 reset 后的显式
   队列初始化能清除状态。未初始化队列返回 `device_closed`，用错 RX/TX 方向返回
   `device_invalid`，避免访问空映射或破坏另一种队列的所有权。

初始化 RX 的 64 个 descriptor 合并为一次批量发布：完成表和 ring 填充后，只更新
一次 avail index，保留发布前后的屏障。原先每个 descriptor 都执行两次屏障，现为
整批两次。运行期仍保留每次发布的顺序约束；此次未做吞吐量或延迟基准测试。

每个队列新增 64 个 4 字节待交付记录及少量状态；内存固定、有界。处理新完成记录
的总工作量为每记录一次，不为每次 `receive` 重扫整批记录。队列容量、帧上限、
DMA 页数和线协议保持原值。生产驱动在收到负错误后仍由服务进入既有 shutdown /
reset / grant close 路径，DMA 回收与 quarantine 责任仍在既有设备契约内。

参考：[VirtIO 1.2](https://docs.oasis-open.org/virtio/virtio/v1.2/virtio-v1.2.html)
§2.7.6 available ring、§2.7.8 used ring、§2.7.13 发布顺序以及 §5.1.6 网络收发；
原始帧范围见 [net_user_driver](../contracts/net_user_driver.md)。

## 验证

工具：Linux x86-64，GCC/G++ `14.2.0`，Python `3.12.14`。宿主工具链仅用于
实现回归与编译检查，未替代仓库固定的 XOS 交叉工具链。

| 检查 | 结果 |
|---|---|
| 新夹具分别对原生产 `.cpp` 运行 `reinitialize_dirty`、`rx_duplicate_batch`、`failure_latched` | 三个回归断言均失败，确认上述缺陷可复现 |
| `python3 tests/virtio_net_host.py` | 14 场景通过 |
| `ASAN_OPTIONS=detect_leaks=0 python3 tests/virtio_net_host.py --sanitize` | 同一 14 场景通过，AddressSanitizer / UndefinedBehaviorSanitizer 无报告 |
| `python3 tests/ipc_device_host.py` | 8 场景通过 |
| `python3 tests/ipc_v1_query_compat_test.py` | 9 场景通过 |
| 宿主 `-ffreestanding -nostdinc++ -fno-exceptions -fno-rtti -mno-red-zone` 编译真实驱动 | 通过，`-Wall -Wextra -Werror` |
| `python3 -m py_compile tests/virtio_net_host.py`、`git diff --check` | 通过 |
| `python3 tests/check_public_evidence_paths.py --index --base origin/main` | PUBLIC_READY |

14 场景覆盖能力解析、TX 队列满与回收、65,540 次 TX index 回绕、RX 最小/最大
边界、坏长度与 offload 头、used 距离、脏内存重新初始化、同批重复 descriptor、
待交付所有权、65,540 次 RX 完成回绕、DMA 元数据快照、故障锁存及方向检查。

首次不加 `detect_leaks=0` 的 sanitizer 运行因 ptrace 环境下 LeakSanitizer 无法
启动而失败。后续显式关闭 leak 检查；内存泄漏检测未取得结果。该夹具的队列与缓冲
为固定存储，不创建堆对象，ASan/UBSan 执行范围仍是实际 parser/split queue。

原始基线失败记录位于 `build/driver_audit/baseline_regressions.json`，宿主编译对象
位于 `build/driver_audit/virtio_net.freestanding.o`；可重新生成，未加入冻结历史报告。

## 待补客体验收

本分支 **guest qualification = not_run**。尚无本次修改对应的固定交叉工具链 /
完整 SDK / 重建系统镜像组合；宿主夹具不执行真实 PCI、MMIO、DMA、IRQ、调度或
设备 reset。后续成员在具备完整环境后执行：

```sh
python3 scripts/build.py --output-dir build/net_driver_audit_system
python3 tests/virtio_net_guest.py --system build/net_driver_audit_system
```

复验 ARP 字节、IRQ、reset 后 close、重复启动/停止资源基线，并在与 N2/N3 组合的
最终镜像补 TCP/UDP 多会话和故障恢复测试。真实设备故障/恶意 DMA、共享 IRQ、SMP
及 IOMMU 隔离仍沿用专项门槛。2026-11-13 的历史原始帧通过结果保留原始输入范围。
