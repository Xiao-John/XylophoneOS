# eaf8370d · Pumpkin authenticated files client

2026-11-26 · 从 `d5591546` 继续。在隔离的 `--files-private-client-probe` 配置中，
files 核对内核认证的启动监督器及其实际子任务后授予独占槽租约。监督器透过私用管道
交付 files 创建的 sys84 端点，客户端核验对端后操作。files 留在不透明槽边界，使用
完整写入、同步和读回确认，账户格式由测试客户端处理。协议、上限和撤销条件见
[受信客户端契约](../contracts/pumpkin_files_client_probe.md)。

## 验证

宿主使用 Apple Clang 21.0.0 与 Python 3.12.15，x86-64 使用目标 GCC 16.2.0，客体用
QEMU 11.1.2。宿主正常和 ASan/UBSan 各过四组。覆盖读写排他、伪造启动会话、非直接
子进程、启动会话撤销、失效端点回收、未提交暂存、同步/读回故障及结果未知。
首次单文件目标检查触发 GCC 对类型复制的诊断，按字节复制修正后以现有严格选项通过。
files、diskio 和监督器的默认配置目标对象也编译通过。现有 ABI 一致性通过。

```sh
python3 tests/pumpkin_files_lease_host.py
python3 tests/pumpkin_files_lease_host.py --sanitize
python3 scripts/build.py --files-private-client-probe --output-dir build/pumpkin_files_client/system
python3 tests/pumpkin_files_client_guest.py --system build/pumpkin_files_client/system --output build/pumpkin_files_client/guest
```

一次性私有测试盘上完成两次 xsh 客体启动，共五项实际验证。直接 `exec` 内置探针
返回 14。通过监督器授予后，写入并读回带单条合成吊销记录的 P0 快照。第二次写者
暂存后退出，新只读租约拒绝暂存请求并读回原快照。正常结束 QEMU 后再启动，重新
授予只读端，快照与完整盘尾均保持一致。各步骤资源回到 `129702 / 3 / 1`。

仅验证隔离试验的授权、槽读写及普通重启。测试角色不接受真实凭据，独立代际及防回滚
仍待实现和验收。物理掉电、写入中断和 dash 未运行。入口来自受信监督器的测试命令，
由同一个内置映像执行。公共文件 ABI 与内核没有新增编码。

| 工件 | SHA-256 |
| --- | --- |
| 系统 `3a3545cfe7c6243b` manifest | `8a39fd295e347672bef82a22ac7a3a5ecfe18a5bfd17e9f5521dc9bdb29af2a5` |
| 系统 ISO | `3bc5eb494e53d50239348bcd689c02243a2d2f143f4dc383b6b49c17cd20527d` |
| SDK 树 | `2cebc37365a46322cf6f0bfa95970964349f99abaacb8187993578a5f69cef5c` |
| files ELF | `4068c78263f0f3d44f64beb67ebd445b48527e0ac151ebecf439af0208657456` |
| 监督器 ELF | `568badc2ca2d53fb930d08d5e3acf3e593992e910773a9e444793b9c461d5161` |
| Pumpkin 探针 ELF | `aa564f01e055364681039f013bc3f00bed35e6aa723b1302b8dd3d60ea5f87bc` |
| `build/pumpkin_files_client/guest/report.json` | `128283ff9a0658ec36ee6f87580d69f49fbac259229556afaed86dd961501704` |
| `build/pumpkin_files_client/guest/boot1_serial.log` | `4ea2aaa1d85139f87c9c192054563682101ad21979cca29465e1047bc93c6077` |
| `build/pumpkin_files_client/guest/boot2_serial.log` | `cfff9edbe9980d242b18b27312394af6f663cfcbca07dda9aa05926125ef8bbd` |
