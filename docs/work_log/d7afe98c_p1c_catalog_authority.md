# d7afe98c P1-C：持久 catalog authority 与后代显式撤权

## 当前状态

实现与 host 检查已经重建；新的成套 GNU runtime/native SDK、23 场 XOS guest
与独立 Linux UID provider 集成仍在验收中。本记录不是 P1-C 完成声明。
不把环境恢复前丢失的构建或旧测试结论附到本轮新字节上。

基线为 main 6332527ab64e92371266363f41f3247717a3cac8，包含已合并 P1-E #442
和 P1-B #443。E 继续提供 16 KiB private slot、完整账户/应用数据/安装 metadata
及 catalog/checkpoint 的单一 protected CAS；本 PR 完成其持久启动授权接线。

## 实现与选择

- 持久 active 切换和显式 active/all-root 撤销，沿用 expected revision/auth/catalog
  epoch；未知结果停止服务而不重放。
- PPR1 追加受真实角色约束的 publisher_checkpoint=12 与 activate_generation=13，
  帧大小、旧编号和 publisher 权限范围不变。
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

公开 JSON 为已标记的可移植派生报告；原报告摘要及转换对应关系见
[host_conversion.json](../reports/p1c_catalog_authority/host_conversion.json)。
LeakSanitizer 在当前 ptrace 环境未运行，不把 detect_leaks=0 声称为内存泄漏验收。

## 待完成验收与已发现夹具问题

tests/pumpkin_catalog_guest.py 计划执行 23 次真实 XOS boot：四类 CAS/ACK 结果
选择完整旧/新根，冷启动实际 GNU ELF，旧磁盘拒绝，真实 reexec 与父/子/孙三代
撤权，独立 native owner 检查，全部撤销恢复，以及 daemon 不可用时拒绝。
仅单元测试通过不足以关闭这些项。

Linux provider gate 使用真实 UID 1001/1002/1003。首轮 preflight 发现 fixture
realm 错写为 17 字节；修正为 16 字节并加断言，生产校验保持原样。后续 VM
已实际通过 strict profile/private root、provider provision、错误 operator
provision 拒绝及私有 record 读取拒绝；只读 9p/TCG 冷 Python 导入超过测试进程
启动预算，正由 root 调整只读映射缓存并重跑。生产 RPC 三秒期限没有调整。
完整 provider 报告尚未通过，不提前记为独立部署完成。

## 交付条件与边界

D 统一重建 capsule v3 shared GNU runtime，C 只读消费其完整摘要绑定的 SDK，
构建两个 GNU C 程序后生成 catalog fixture，再构建隔离系统并执行上述矩阵。
运行结束重新核对源、runtime、SDK、generation 和系统输入；flat evidence
index 与实际暂存 public-path gate 通过后才可作为可合并交付。

持久存储的开发 authority、真实 Linux UID isolation、用户物理宿主部署和
任意掉电分开报告。没有执行物理断电资格；sync/reboot 或 host kill 不替代它。
本任务不修改 docs/state.md，由 root 统一记录全局进度与最终 PR/merge 身份。
