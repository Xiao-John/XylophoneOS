# ef27c642 · Pumpkin durable daemon test

2026-11-26 · 从受信客户端 `610f5fdf` 继续，并纳入 P1 评审修复。隔离构建将 P0
账户存储接到真实 files 租约，使用本地双槽校验和重启选择。授权、故障边界与生产
防回滚的前置条件见 [守护进程测试契约](../contracts/pumpkin_durable_daemon_probe.md)。

## 验证

使用 Apple Clang 21.0.0、Python 3.12.15、目标 GCC 16.2.0 和 QEMU 11.1.2。
宿主普通及 ASan/UBSan 各通过两组本地双槽检查。原核心与发布器的十二组回归、目标
对象编译、P1 邮箱 ASan/UBSan 和 ABI 一致性均通过。

```sh
python3 tests/pumpkin_disk_test_store_host.py
python3 tests/pumpkin_disk_test_store_host.py --sanitize
python3 scripts/build.py --pumpkin-durable-probe --output-dir build/pumpkin_durable_stage/system
python3 scripts/build_dash.py --sdk build/pumpkin_durable_stage/system/sdk --archive "${XOS_DASH_ARCHIVE}" --receipt build/pumpkin_durable_stage/dash.json
python3 tests/pumpkin_durable_daemon_guest.py --system build/pumpkin_durable_stage/system --dash-receipt build/pumpkin_durable_stage/dash.json --output build/pumpkin_durable_stage/guest
```

初次尝试在宿主可用空间不足时未创建构建目录。随后使用 128 MiB 内存盘暂存一个系统
与对应编译临时目录。QEMU 使用一次性稀疏工作盘。测试完成后保留确切 ISO、程序、
清单、串口及压缩 SDK，重新展开验证 SDK 树摘要，释放内存盘。

xsh 执行可信启动授予，实际守护进程从 sys63 产生登记密钥，并验证错误密钥与正确
认证。用同一测试密钥在守护进程重启后再次认证。dash 编译自同套 SDK，从私用管道
继承密钥，普通客户端认证并注销。登记端吊销已登记用户、核对旧会话失效和旧密钥
拒绝。再启动守护进程时仍保留吊销，原密钥继续拒绝。正常结束 QEMU 后在同一盘上
完整重启，重新授予后查询相同吊销记录，两个槽逐字节相同。资源在两次入口均回到
`129696 / 3 / 1`。

本轮登记使用真实熵源，但凭据的输入、保管与分发只走测试进程内存和私有 IPC，
没有将真实密钥带过完整 QEMU 重启。生产登记流程、独立防回滚、物理断电和写入
中断仍待专项验收。

| 工件 | SHA-256 |
| --- | --- |
| 系统 `e2fdb38e6cb83130` manifest | `d248a7db810bbe04466cf69677293ce59fd28cd93cbfe423a88b88e33d9e7599` |
| 系统 ISO | `d8ad45ff81cd1511234dc0cd41fd4af7ff356ad361761a00dc86ccba1e066b55` |
| SDK 树 | `70135c48483ba1a7c6e619830b3b5bddf2e0cf1a9a03dccb95a428989257384d` |
| 守护进程 ELF | `68465110042e55c6c584a24e43ca8b693036bce1f6e66c08752c81f1c4eeb1d5` |
| dash 客户端 ELF | `4493a9d23c761f0f6294629c85799410806de28c7eb162b9aac6c06b119ce9bc` |
| `build/pumpkin_durable/guest/report.json` | `251813d5665d2809aadd9aa55947b57781e981bda559acd793e319ca1c214f6c` |
| `build/pumpkin_durable/guest/cycle_serial.log` | `7c4a750566cd1deab20e80eee3810c6c517ef4763a530143112b6f7508de6d73` |
| `build/pumpkin_durable/guest/check_serial.log` | `be5067837e97fa596f9995974a31b5e53c2b87eeb28e27482fe0cbb0c9a08898` |
