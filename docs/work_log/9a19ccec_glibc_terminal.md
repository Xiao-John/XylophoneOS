# 9a19ccec — glibc terminal 真实阻塞与验收来源评审修复

日期：2026-11-25。基线 `5dafaae`，对应 PR #163 review comments
`4694700245`（宿主来源绑定）与 `4694700227`（真实阻塞读）。本组修改 tests
与证据，不改变生产 libc、终端协议、创建权限或 SDK 内容。

## 宿主来源绑定

旧 runner 在编译、执行结束后才取摘要。专用回归复制必要输入，在真实 C++
最终链接成功后给 `terminal_runtime.cpp` 追加注释：旧脚本返回 0 并把 passed
绑定到新摘要，复现评审所指问题。修后在首条编译命令前固定 89 项实际编译
来源和仓库头文件，通过前重新收集比较；相同注入返回 1 / failed，报告保留
原始 `sources` 与变化后的 `sources_after`。普通与 ASan/UBSan 各 23 组通过，
`source_snapshot_verified=true`。生产终端/文件运行时字节保持原样。

## 真正的阻塞顺序

`reader_started` 只表示工作线程将调用 read，旧宿主在 BLOCK_READY 后发送
输入也会提前解除等待。现在 fixture 只创建 main 与 reader 两个线程，main
通过已有只读 sys50 查询本进程线程状态。只有 reader 已进入 read 路径且
`threads=2, waiting=1` 才执行文件 open/write/seek/read/close/unlink；文件
操作完成后再次要求同样的计数，reader 仍未完成。main 的 sys50 调用同步
返回，自身不处于 blocked 状态，所以唯一 waiting 线程就是 reader。

该等待与宿主输入之间使用独立的文件观测通路：

1. 启动前在私有 FAT32 盘创建每轮独立的 512 字节文件，验证单 cluster 分配、
   文件大小及初始全零内容，并记录其数据扇区位置。对实际传入 QEMU 的同一
   磁盘计算初始散列。每轮生成独立 128-bit nonce，路径和扇区也互不复用。
2. 文件操作通过、第二次等待计数确认后，fixture 设置 `file_progress=1`，
   将两次 threads/waiting、进展值和 nonce 写成一条 512 字节记录并 fsync。
   记录末尾填满非零 `0xa5` 哨兵，避免把部分写当成完整记录。
3. QEMU 运行期间，宿主只以只读方式访问预先确定的数据扇区，不再查询 FAT
   元数据、不运行离线 transfer 工具、不写运行盘。完整 512 字节必须精确
   匹配当前 nonce 对应的记录，之后才发送 ESC[A。

超时用于判定缺失进展，允许输入的条件始终是实际记录。输入事件记录包含
前后等待计数、file_progress、扇区 offset、nonce、实际与预期 SHA-256。
终端 I/O 仍通过公开 glibc 接口和原认证应用通道完成。

## 故障变体与先前失败

`glibc_terminal_blocking_negative.py` 在私有目录复制 file runtime，定点把
terminal read 的 files 锁释放改为持锁等待。只将这一故障对象作为额外 TU
链接到标记为 diagnostic 的 ELF；原 SDK、库和工作区源码不变。变体运行相同
公共 fixture 和宿主 gate。结果为 5 秒内进展记录缺失、观测扇区仍全零、
宿主注入输入 0 字节，成功检测持锁缺陷。这个结果记录为
`passed_negative_detection`，故障程序本身保持未通过状态。

首次方案尝试在 read 等待期间用 sys1 输出诊断，正向和故障变体都退出 91。
核实后发现 tty-run 显式关闭 child 原生 stdio，COM1 又由终端服务接管。
生产权限按契约拒绝这条通路，因此改用上述只读磁盘观测，没有放宽 tty-run
授权或向 terminal session 并发插入额外请求。两份失败报告和串口均已保留。

## 实际结果与来源

| 检查 | 实际结果 |
|---|---|
| 旧/新宿主 runner 链接后输入变更 | 旧 false pass 复现；修后失败并保留原摘要 |
| 生产终端、FD、termios 宿主测试 | 23 / 23 通过 |
| 同组 ASan/UBSan | 23 / 23 通过 |
| 新观测文件离线分配检查 | 3 个文件，独立扇区与 nonce |
| 公开终端客体 | 3 次通过，全部完整观测记录先于输入 |
| native→glibc exec 终端继承 | 3 次通过 |
| 每次正向客体的资源恢复 | 129533 free pages、4 tasks、2 completions |
| 真实持锁故障变体 | 进展 gate 超时；扇区未改；输入 0 字节 |

最终系统 build ID `b7f3b54fba6a0103`，kernel 825496 字节。复用完整
`terminal_sdk_initial`，输入集合与所有已安装产物在运行前后核对；无 SDK
内容修改。宿主 GCC/G++ 14.2.0；preview 目标 GCC/G++ 16.2.0、binutils
2.47.20260726、NASM 3.02；实际 QEMU 11.1.3，仓库锁版本 11.1.2。
serial-only，QMP 关闭。LSan、物理机器、锁定 QEMU 版本及后续组合 SDK 的
终端客体验收留给各自明确的资格阶段。

| 原始对象 | SHA-256 |
|---|---|
| SDK manifest | `ade36f38cd935c9638bd91515208920ccc97a238edec66386cdb2ab49fbb8add` |
| 系统 manifest | `d36eb74fb2f62cec38a90dbb2b0ff4d8e052d1ea03d40f281437ed0d6f36d6c6` |
| 正向客体 report | `463c7a81e611ecc3035c30daeaa24e8fa3ce6510f5055b2658efba15bd8f57c6` |
| 故障变体 report | `e5e1c80ebef8108afa68a482ae583b8810971a4f3be0261e9a2e53d86cf83d5b` |

冻结证据在 [glibc_terminal_review_20261125](../reports/glibc_terminal_review_20261125/manifest.json)。
根清单绑定所有叶子；`qualification.json` 保存原始散列与路径模板化关系。
公开日志规范化 CRLF/行尾空白；旧失败、成功和故障注入分别保存。

## 已执行命令

`XOS_PREVIEW_RUN` 为 preview 工具执行入口，`XOS_PR163_PRE_REVIEW` 为本次
评审修复之前的 PR #163 版本。输出目录要求为空。

```sh
python3 tests/glibc_host_source_binding.py --profile terminal \
  --baseline "${XOS_PR163_PRE_REVIEW}" --expect passed --output build/terminal_source_binding_before
python3 tests/glibc_host_source_binding.py --profile terminal --output build/terminal_source_binding_after
python3 tests/glibc_terminal_host.py --output build/terminal_host_review
python3 tests/glibc_terminal_host.py --sanitize --output build/terminal_host_review_sanitized
"${XOS_PREVIEW_RUN}" python3 scripts/build.py --output-dir build/terminal_system_sector
"${XOS_PREVIEW_RUN}" python3 tests/glibc_terminal_guest.py \
  --system-build build/terminal_system_sector --glibc-build build/terminal_sdk_initial \
  --output build/terminal_guest_sector --repetitions 3
"${XOS_PREVIEW_RUN}" python3 tests/glibc_terminal_blocking_negative.py \
  --system-build build/terminal_system_sector --glibc-build build/terminal_sdk_initial \
  --output build/terminal_blocking_negative_sector
python3 scripts/verify_evidence_index.py docs/reports/glibc_terminal_review_20261125/manifest.json
python3 tests/check_public_evidence_paths.py --commit HEAD --base 5dafaae \
  --output build/terminal_review_public.json
```

下一位整合者将 tests 变更合入组合后重新构建系统并单独运行终端套件；SDK
输入若保持原字节可以继续使用已完成的成套 SDK。process runtime 已拥有全局
`.xos.exec` 的分支，应继续删除本 fixture 开头仅供旧 receiver 的条件标记；
该删除与本次主体改动独立。共享来源变更探针与 PR #160 使用同一文件；组合
中已补入更多实际编译依赖时保留那些输入。root 负责更新原 PR 和全局 state。
