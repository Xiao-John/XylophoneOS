# P1-F 主线启动清理整合证据

在主线 `93758f59488c32161cc15b909513a91106408cf1` 上整合 F checkpoint6
`a3874f94616f6ffbed368d39d9e6bb21ebb9ee9d`，新 native test image `7117377f147d895c`
实际通过原来的 21 个启动失败清理场景：20 次实际 kernel start 失败后，
精确 abort 成功、撤销项释放及资源回收；1 次第二次 abort 失败后保留拒绝项。
全过程未观察到 child 的启动标记。

| 文件 | 内容 |
| --- | --- |
| `report.json` | 父提交、实际场景数、资源基线和资格边界 |
| `source_compatibility.json` | 95 个 F 输入路径、7 个共享合并路径及 G/K5/I1/C/D 保留检查 |
| `native_system.json` | 新 native 系统的完整 source/artifact manifest 公开投影 |
| `execution_receipt.json` | SDK 命令、精确源快照、冻结输入前后核对及临时空间策略 |
| `guest.json` | 原 runner 对新镜像的 21 个实际场景完整报告 |
| `serial.json` | 新 guest 原始 serial 的无损 base64、原摘要及长度 |
| `supervisor_strip.json` | 新 native supervisor 的完整 entry/PT_LOAD 字节等同性证明 |
| `frozen_child_build.json` | 旧 child 自己的 source/SDK 构建身份，未重新绑定新主线 |
| `frozen_child_strip.json` | 旧 child 的剥离边界；首次 LOAD 内只有 ELF 节表字段变化 |
| `preflight_attempts.json` | 两次进入 target 编译前的编排失败，未计入 21 场景 |
| `diff_gate.json` | 六份冻结原 serial 的空白检查说明及源码/新证据检查 |
| `conversion.json` | 原始回执与公开投影摘要、路径模板和转换定义 |
| `manifest.json` | 本目录其余文件的 flat SHA-256/长度清单 |

`source_tree_before_gate_evidence` 为
`8d107bf92105f46b9b3d5514cf92a36707361376`。两个文本冲突仅在构建入口，C 的
catalog/launch/lease 与 F 的 ClarkE 参数同时保留。88 个 F 路径逐字节保留，
7 个共享路径分别完成合并；F 路径以外的主线内容没有覆盖。G 窗口服务、
K5 默认管道选项与可选实现、I1 resolver 接线、C/D 已合入实现均保留。

原生 test image 和原 child 是两个独立身份。child 仍为 609,008 bytes、
SHA-256 `a8fe1fc3cf5f3c0396ab63d7b5c9c6c34364858fe520f746b7c325dcc3a3660b`，原 source/SDK/strip receipt、旧 native
manifest 和历史 21-case 报告全部保持不变。新镜像单独绑定当前 native
源码，不能据此把旧 GNU 产物重标成新 SDK 构建。

本轮使用 K5 的默认 `transfer_independent_pipes=false`，证明已集成 K5
实现的 legacy 分支仍满足原启动清理契约，不授予可选 pipe-transfer、I1
DNS failover 或完整 ClarkE 浏览器资格。完整浏览器验收后续使用独立
`--clarke-bundle` 镜像，不能携带此次 `BAD_START_ENTRY` test flag。

## 实际资源和网络边界

资源元组依次为 free pages / live tasks / completion records。冷启动为
`[129673, 3, 1]`，初始化后为
`[129672, 3, 1]`，第二次普通网络启停为
`[129672, 3, 1]`。首次分配的
`1` 页属于内核每次 boot
缓存的 PCI reset-status observer；这是实际两次普通网络生命周期分离出的
数值，不通过放宽每次进程回收条件吸收。21 场景所用服务前后资源完全相等：
`[129672, 3, 1]` → `[129672, 3, 1]`。

网络沿用 `net-start 41`，默认 10.0.2.15/24、gateway 10.0.2.2，主/备用
resolver 均为 0。没有 static、DHCP 或 DNS probe profile，因此不进入 I1
新 failover 路径。没有修改生产 quota、RPC deadline、21-case runner 或
启动/清理接受条件。

## 重现与证据验证

原构建器要求输出位于源树 `build/` 内。编排先在 SDK invocation 的临时
文件系统创建逐 SHA 相等的源快照，再调用未修改的构建入口；guest FAT
及可重建对象只存在该 invocation 中。最终 ELF/ISO、source/SDK manifest
和原始日志通过逐文件前后摘要复制回工作目录。没有复制额外 GNU SDK，
没有删除原 producer 或历史报告。

精确命令及可配置位置见 `execution_receipt.json` / `conversion.json`。
JSON 投影只转换安装前缀和排版，原回执不变。serial 先 base64 解码，再
检查原长度和摘要；外层 JSON 摘要另由 flat manifest 绑定。

```sh
python3 scripts/verify_evidence_index.py docs/reports/p1f_main_integration/manifest.json
python3 tests/check_public_evidence_paths.py --index --base 93758f59488c32161cc15b909513a91106408cf1
```

完整记录见 `docs/work_log/b86e41c2_p1f_main_launch_integration.md`。
