# VirtIO-net 原始帧纵切客体复核（2026-11-13）

`docs/contracts/net_user_driver.md` 原记录为 `guest qualification=not_run`。本次在加固后的
main 上重跑：

```sh
python3 scripts/build.py --output-dir build/ipc_device_system
python3 tests/virtio_net_guest.py --system build/ipc_device_system
```

结果（原始 `report.json` 见同目录）：

```text
status=passed
guest_qualification=passed_with_limits
checks:
  user_driver_tx_rx_irq_reset_release_0
  user_driver_tx_rx_irq_reset_release_1
  user_driver_tx_rx_irq_reset_release_2
not_run: tcp, dns, tls, untrusted_dma_isolation
```

含义：真实 ARP TX/RX（网关 `10.0.2.2` 回复）、至少一次 IRQ、reset 后 grant 释放、
连续三轮资源基线稳定。TCP/DNS/TLS 与不可信 DMA 隔离仍未验证——TCP 现已由
[lwIP 端口](../lwip_2_2_1_20261113/README.md) 的 ICMP 用例向前推进一层，但 lwIP 的
TCP 尚无客体证据。
