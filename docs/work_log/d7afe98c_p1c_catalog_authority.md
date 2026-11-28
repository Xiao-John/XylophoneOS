# d7afe98c P1-C：持久 catalog authority 与后代显式撤权

## 当前状态

实现与 host 检查已经重建；独立 Linux UID provider 集成已经通过。新的成套
GNU runtime/native SDK 与 23 场 XOS guest 仍在验收中。本记录不是 P1-C 完成声明。
不把环境恢复前丢失的构建或旧测试结论附到本轮新字节上。

基线为 main 6332527ab64e92371266363f41f3247717a3cac8，包含已合并 P1-E #442
和 P1-B #443。E 继续提供 16 KiB private slot、完整账户/应用数据/安装 metadata
及 catalog/checkpoint 的单一 protected CAS；本 PR 完成其持久启动授权接线。

## 实现与选择

- 持久 active 切换和显式 active/all-root 撤销，沿用 expected revision/auth/catalog
  epoch；未知结果停止服务而不重放。
- PPR1 追加受真实角色约束的 publisher_checkpoint=12 与 activate_generation=13，
  帧大小、旧编号和 publisher 权限范围不变。
- D 的冻结 distribution_startup.hpp 轻头先由本 foundation PR 交付，避免新
  runtime/native SDK 的源闭包依赖未合并文件。它只有96字节四阶段消息布局；
  D controller/验签/staging 实现不混入本 PR。该头原始 SHA-256 为
  b1053206fdddb8a030ddfb1927fc894d733541f750fe33de92a52aa143745910。
- PCQ1 以真实 named IPC 的两端 kernel peer、realm、版本和期限核对当前 catalog。
  动态 capsule 明确升级 v3，加入完整 authority binding；自身 owner、current
  和目标 artifact 均须仍受批准，避免新子进程空 current 绕过父根撤销。
- fork 后建立新连接，exec 从新 capsule 恢复自身身份；受信 SDK 路径和有限
  grant-to-commit 语义见 [专项契约](../contracts/pumpkin_catalog_authority.md)。
- Linux provider 使用显式 strict v2 profile，禁止 v1 自动格式升级；不同真实 UID
  与 SO_PEERCRED 验证由单独 Linux VM gate 检查。
- 专用 catalog/distribution 夹具将 supervisor/proxy 控制消息迁到现有 sys84
  named pair，实际 parent/child 身份加精确 PPC1 HELLO/ACK。daemon/proxy backing
  仍走 sys81，普通 E/P2 profile 不变，内核容量不增加。原因是原主管持有四个
  sys81 endpoint，真实动态 READY/ACK 无法再创建。C 夹具在启动前枚举并要求
  主管仅持有 backing 的两个 sys81 endpoint；真正 GNU launch 仍须成功。

## 本轮已执行

所有编译使用已发布 glibc preview-3 SDK 环境；host 检查编译生产源。可移植命令：

    python3 -B tests/pumpkin_provisioning_host.py --output build/p1c-provisioning-host
    ASAN_OPTIONS=detect_leaks=0 python3 -B tests/pumpkin_provisioning_host.py --sanitize --output build/p1c-provisioning-asan
    python3 -B tests/pumpkin_catalog_authority_host.py --output build/p1c-authority-host
    python3 -B tests/dynamic_closure_host.py --output build/p1c-closure-host

| 检查 | 本轮结果 | 证据 |
|---|---|---|
| 生产 store/codec/RPC 普通及 ASan/UBSan | 2 轮通过；含 publisher 权限、持久 active、最后根撤销和 cold decode | [provisioning_host.json](../reports/p1c_catalog_authority/provisioning_host.json) |
| PCQ1 生产 reader/admission，模型 kernel transport | 9 普通 + 9 ASan/UBSan 通过 | [authority_host.json](../reports/p1c_catalog_authority/authority_host.json) |
| 生产 closure/ELF，模型 Files OFD | 23 普通 + 23 ASan/UBSan 通过 | [closure_host.json](../reports/p1c_catalog_authority/closure_host.json) |
| 新 PCQ1 server、catalog supervisor 与 sys84 proxy | SDK 交叉编译通过 | 尚不能替代实际 guest |
| 独立 Linux VM provider v2 | 12 项功能检查与 3 项实际进程启动计时通过；真实 UID 1001/1002/1003 | [provider_report.json](../reports/p1c_catalog_authority/provider_report.json) |

公开 JSON 为已标记的可移植派生报告；原报告摘要及转换对应关系见
[host_conversion.json](../reports/p1c_catalog_authority/host_conversion.json)。
LeakSanitizer 在当前 ptrace 环境未运行，不把 detect_leaks=0 声称为内存泄漏验收。

## 待完成验收与已发现夹具问题

tests/pumpkin_catalog_guest.py 计划执行 23 次真实 XOS boot：四类 CAS/ACK 结果
选择完整旧/新根，冷启动实际 GNU ELF，旧磁盘拒绝，真实 reexec 与父/子/孙三代
撤权，独立 native owner 检查，全部撤销恢复，以及 daemon 不可用时拒绝。
仅单元测试通过不足以关闭这些项。

Linux provider gate 使用真实 UID 1001/1002/1003。首轮 preflight 发现 fixture
realm 错写为 17 字节；修正为 16 字节并加断言，生产校验保持原样。早期只读
9p/TCG 冷 Python 导入超过夹具启动预算，最终以发布 SDK 中的 QEMU、Linux
动态 loader 与全部依赖直接启动真实 Linux VM，未使用 proot 伪造 UID。
成功轮 recovered6 的 QEMU 和测试均以 0 退出；完整 v2 mark CAS、拒绝 stale
CAS、进程重启恢复、错误 UID 和错误格式均通过。冒充 provider 在被拒绝前
收到零协议字节。三次实际进程就绪时间为 5.56、13.44、15.36 秒，位于专用
夹具 30 秒启动预算内；生产 RPC 三秒期限没有调整。

该 VM 只读挂载 SDK 与冻结源码，所有测试可写状态在 guest tmpfs。它证明
真实 Linux UID/SO_PEERCRED 隔离和 provider v2 恢复，不证明物理宿主部署或
任意掉电。mark 使用明确的合成完整值，实际 XOS 应用数据由另一个 guest
gate 检查。原日志摘要、失败轮摘要、kernel/initramfs/SDK/QEMU 及源码绑定
见 [provider_vm_receipt.json](../reports/p1c_catalog_authority/provider_vm_receipt.json)
与同目录 flat manifest；没有把前五轮失败改记为通过。

## 交付条件与边界

D 统一重建 capsule v3 shared GNU runtime，C 只读消费。该 runtime 绑定 F
GNU SDK，native PIC 直接从 154 项冻结源码编译，不依赖 D 整系统 native
SDK；这 154 项以及 recipe/port 输入均须与 C 单树逐项一致。C 另行从自己的
隔离源树构建 native SDK，避免应用 bootstrap 来源绑定未合并 D 系统的
build_id。随后构建两个 GNU C 程序，生成 catalog fixture、构建隔离系统
并执行上述矩阵。保留原 runtime manifest，绝不重新标记其生产来源。
运行结束重新核对源、runtime、SDK、generation 和系统输入；flat evidence
index 与实际暂存 public-path gate 通过后才可作为可合并交付。

持久存储的开发 authority、真实 Linux UID isolation、用户物理宿主部署和
任意掉电分开报告。没有执行物理断电资格；sync/reboot 或 host kill 不替代它。
本任务不修改 docs/state.md，由 root 统一记录全局进度与最终 PR/merge 身份。
