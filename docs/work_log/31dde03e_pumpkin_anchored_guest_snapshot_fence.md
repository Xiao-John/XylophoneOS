# 31dde03e · Pumpkin 旧盘快照期间保留客体回复期限

2026-11-26 · 从 `f8c7a0f6` 继续。原测试在持久提交修订 2 之后、回复客体之前，扫描、复制并核对整个工作盘。宿主接收下一帧可等十二秒，但代理串口和守护进程 IPC 的单次交换期限均为六秒，宿主复制此前占用客体期限。

本次在固件提示阶段先建立 QMP。修订 2 的槽同步和读回后，宿主持久提交盘外的代际记录，再执行 QMP `stop`。收到 `query-status` 的 `paused` 后才复制、同步并核对旧盘。核对通过后执行 `cont` 并回复修订 2，客体随后才发起导致修订 3 的吊销。`sys_clock_monotonic` 来自 `src/kernel/core/clock.cpp` 的 IRQ0 计数。暂停时没有客体定时中断，宿主慢复制仍处在真实修订 2 提交与修订 3 写入之间。

```sh
python3 -B scripts/build.py --pumpkin-anchored-probe --output-dir build/anchor-fenced-system
python3 -B tests/pumpkin_anchored_guest.py \
  --system build/anchor-fenced-system --output build/anchor-fenced-regular
python3 -B tests/pumpkin_anchored_guest.py --slow-snapshot \
  --system build/anchor-fenced-system --output build/anchor-fenced-slow
python3 -B tests/abi_doc_consistency.py
```

从 `9a82643b` 构建，系统清单中唯一变动的源文件是验收脚本。files、监督器、守护进程和代理的 ELF 与前次逐字节一致。QEMU 11.1.2 中两轮共六个全新启动通过。普通快照在暂停内耗时 1.373 秒，注入七秒等待的快照在暂停内耗时 8.104 秒。两轮首次启动均顺序提交修订 1、2、3。每轮新启动的当前盘确认吊销仍在，完整旧盘启动拒绝过期状态。两种重启的输入盘和输出盘分别同哈希，盘外权威保持修订 3。ABI 表核对通过。

| 工件 | SHA-256 |
| --- | --- |
| 系统 `6b2839f2c6b9b86f` manifest | `57638b1cbf1bb17447f4316ad191b8acd7a925ff07eab522fc9542231c46a435` |
| 系统 ISO | `21781ab4b0550acea67ac9169d0ae39cc760bf2ad62cb55f88f93944e36e7c7a` |
| 验收脚本 | `41865fad3220ded7dc8a4321cca398e3147091963ca8d6f09bdcc270a0faac66` |
| `build/anchor-fenced-regular/report.json` | `05b48577f05e18612e5cd26c8700c6b3b306bb0b0efaa7663bab30b9fce114a7` |
| `build/anchor-fenced-slow/report.json` | `5c88bc72968d917e8f5bcdd9cf5d4a54d8261d68b5e1fd8884b4e9247715f2dd` |
| 延迟轮当前盘 | `c47b9063ccb36abfafcbc09bad8883ea4d5c72e9d63d143e46a07ec771d6ba0d` |
| 延迟轮完整旧盘 | `5c302861e37914edb058ac6f956bd8fdda2ba08064b7d455b82347949af01ce9` |
