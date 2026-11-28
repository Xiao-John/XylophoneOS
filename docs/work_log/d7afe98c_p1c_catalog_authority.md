# d7afe98c P1-C：持久 catalog authority 与后代显式撤权

## 当前状态

本轮 P1-C 验收已完成：23/23 场真实 XOS guest 通过，独立 Linux UID provider
集成通过，生产代码 host 检查与对应 ASan/UBSan 检查通过。真实三代 GNU 进程
在撤销前均可启动，撤销后均拒绝；冷恢复与未知结果选择了完整的旧或新 catalog。
所有结果来自本轮重新构建的字节，不引用环境恢复前丢失的产物作为通过证据。
PR 发布与合并由 root 统一执行，本记录不提前声称远端已合并。

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
- 每次 admission 建立新连接，exec 从新 capsule 恢复自身身份；真实后代由
  GNU posix_spawn 创建。shared GNU fork 当前仍返回 ENOSYS，归独立 P1-K2
  composition，未在本 PR 启用或声称通过。受信 SDK 路径和有限
  grant-to-commit 语义见 [专项契约](../contracts/pumpkin_catalog_authority.md)。
- Linux provider 使用显式 strict v2 profile，禁止 v1 自动格式升级；不同真实 UID
  与 SO_PEERCRED 验证由单独 Linux VM gate 检查。
- 专用 catalog/distribution 夹具将 supervisor/proxy 控制消息迁到现有 sys84
  named pair，实际 parent/child 身份加精确 PPC1 HELLO/ACK。daemon/proxy backing
  仍走 sys81，普通 E/P2 profile 不变，内核容量不增加。原因是原主管持有四个
  sys81 endpoint，真实动态 READY/ACK 无法再创建。C 夹具记录 backing 两个
  create 返回的 handle，双方从 kernel 核对 peer/owner；启动前与回收后要求
  主管作为 sender/receiver 参与且 owner 为自身的可见 sys81 endpoint 为零。
  channel_get 不枚举仅由主管所有的第三方 pair，因此不把可见数量当成总
  owner 数量；真正 GNU READY/ACK 和 launch 仍须成功。

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
| 真实 XOS + Files/daemon + GNU 动态程序 | 23/23 次启动通过；含冷恢复、三代撤销和 daemon 不可用 | [guest_report.json](../reports/p1c_catalog_authority/guest_report.json) |
| 独立 Linux VM provider v2 | 12 项功能检查与 3 项实际进程启动计时通过；真实 UID 1001/1002/1003 | [provider_report.json](../reports/p1c_catalog_authority/provider_report.json) |
| Files lease 普通及 ASan/UBSan | 2 轮通过，含默认 30 秒、desktop 1860 秒、显式 launch 300 秒与 controller 死亡；2 项非法 CLI 组合拒绝 | [launch_lease_host.json](../reports/p1c_catalog_authority/launch_lease_host.json) |

Host JSON 为已标记的可移植派生报告；原报告摘要及转换对应关系见
[host_conversion.json](../reports/p1c_catalog_authority/host_conversion.json)。
LeakSanitizer 在当前 ptrace 环境未运行，不把 detect_leaks=0 声称为内存泄漏验收。

## 真实 guest 矩阵与诊断记录

最小 GNU gate 的首轮 initial 已实际提交 catalog 到 revision 2，但在启动前
以 finish=15 拒绝继续。该轮暴露了夹具对 sys81 enumeration 的误读：仅 owner
而不参与收发的 daemon/proxy pair 不可由主管枚举。已纠正观测口径并保留
失败记录；没有改变内核配额，也没有把该轮记成 GNU 启动通过。

修正枚举后两个真实 initial 均通过：持久 revision 2、PCQ/install_anchored、
GNU READY/ACK、generation 201 的实际退出和通道回收。随后 v3 诊断以
finish=186 取得实际 child exit=5：父进程已完成同 PID exec 与一次成功叶子
启动，第一次 fork 失败。冻结 shared libc 的 fork.c/_Fork.c 明确以 SHARED
分支返回 ENOSYS。按 P1-C 原计划，验收对象是跨后代显式撤权；改用真实 GNU
posix_spawn 父/子/孙树，不启用另属 P1-K2 的 shared fork/composition。

D 的旧 profile 在约 33.5 秒出现最终 CAS 的死 endpoint；30 秒 backing
lease 与源码到期链是明确的原因推断，不把未取到的串口诊断当成观察事实。
C/D 统一显式 --pumpkin-launch-storage-lease 的固定 300 秒 profile，并在
最终 guest manifest 中绑定；本次 23 场均明确选择该 profile 并通过。默认
30 秒和 desktop 1860 秒不变，每次 RPC 期限不变，不增加续租或自动重放。

tests/pumpkin_catalog_guest.py 已完成以下 23 次真实 XOS boot，全部 finish=1：

| 场景组 | 启动数 | 实际恢复与运行结果 |
|---|---:|---|
| 正常 CAS 提交 | 4 | revision 3 / generation 202；新根真实启动，旧磁盘拒绝 |
| CAS 明确拒绝 | 3 | revision 2 / generation 201；旧根真实启动 |
| 已提交、答复未知 | 4 | revision 3 / generation 202；新根真实启动，旧磁盘拒绝 |
| 未提交、答复未知 | 3 | revision 2 / generation 201；旧根真实启动 |
| live revoke 与全部根撤销 | 7 | 三代 GNU 前可启动、后拒绝；native owner 前后检查；cold revoked 与 cold all-revoked 拒绝 |
| daemon 不可用 | 2 | 三代先各自真实启动叶子，daemon 停止后全部拒绝新启动 |

三代测试先完成父进程原 PID exec，再以 GNU posix_spawn 产生子进程和孙进程。
主管收到三个实际就绪字节后才提交撤销或停止 daemon；三代分别返回拒绝结果，
最后均以 0 退出。全部场景的原始事务事件、finish code、revision、QEMU 版本
及串口日志摘要见 [guest_boots.json](../reports/p1c_catalog_authority/guest_boots.json)。
两个 generation 使用相同探针程序、不同的 manifest ID/摘要和 guest 主程序路径，
因此这里证明完整 catalog 选择和指定根的实际启动，不声称两个不同产品版本的行为。

选中系统 build_id 为 6477a33592698159，manifest 摘要为
8b580a5dc75f2ce90b4a5a4c14eae01d7390a685025993baa058b92eb7dbcea5。
运行后逐项复核 2,309 项系统源码、320 项系统产物、共享 runtime 的 154 项 native、
14 项 recipe、303 项 port 输入和 9 项产物，均与原始绑定相符。主管 strip 只去掉
非加载节；所有 PT_LOAD 字节和布局保持相同，最终 123728 字节，原 131072 字节
上限未改变。完整来源与所选 300 秒 profile 见
[system_build.json](../reports/p1c_catalog_authority/system_build.json) 和
[guest_conversion.json](../reports/p1c_catalog_authority/guest_conversion.json)。

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

## 构建来源、复跑与边界

D 统一构建 capsule v3 shared GNU runtime，C 只读消费。原始 manifest 摘要
a7a6360491bb8ebe13b85aab61be7d61d0cd26137d1f02f433d7ca908e8bd0dc 保持不变。
该 runtime 绑定 F GNU SDK，native PIC 直接从 154 项冻结源码编译，不依赖
D 整系统 native SDK；154/14/303 项源码已与 C 逐项核对。C 的独立 native SDK
用于应用 bootstrap，原始 manifest 摘要为
d2f47f5e16cd7b36da3e1e8e969f91639dad122751674ed6bebf23ad7ca9fce4。
该 SDK 的源 checkpoint 2e577093222250d49ca6104e5179e4e76242a624 保留在本次
交付祖先中；不能把共享 GNU runtime 重新标记为由此 native SDK 构建。
具体来源、31 个 archive member 的捕获源核对及全部 runtime 输入见
[build_bindings.json](../reports/p1c_catalog_authority/build_bindings.json)。

程序原构建清单保持 built_not_run，runtime 保持 public_runtime_built_not_run；
上述匹配字节的运行资格单独记录在 guest_report.json。程序命令和 SDK/ELF/generation 完整摘要见
[program_201.json](../reports/p1c_catalog_authority/program_201.json) 与
[program_202.json](../reports/p1c_catalog_authority/program_202.json)。
按这些实际源和 SDK 绑定构建后，完整矩阵命令为：

    XOS_QMP_TRANSPORT=pipe python3 -B tests/pumpkin_catalog_guest.py \
      --system-build build/catalog-system \
      --program-build build/p1c-program-201 --program-build build/p1c-program-202 \
      --catalog-fixture build/p1c-catalog-fixture.json --output build/p1c-catalog-guest

系统构建必须显式选择 --pumpkin-anchored-probe、--pumpkin-provisioning-store、
--pumpkin-catalog-fixture 和 --pumpkin-launch-storage-lease；程序构建所用的
profile/manifest/tree/ABI 摘要必须一致，不能只替换某个 JSON 标签。独立 provider
检查使用 tests/pumpkin_provisioning_provider_host.py，须在可创建真实非 root UID
的 Linux 环境执行；此次使用真实 Linux VM，未在用户物理宿主上改变权限。

最终 flat manifest 和实际暂存 public-path gate 由本轮真实 index 检查后交付；
不修改原始构建清单的状态，也不省略原失败诊断。

持久存储的开发 authority、真实 Linux UID isolation、用户物理宿主部署和
任意掉电分开报告。没有执行物理断电资格；sync/reboot 或 host kill 不替代它。
本任务不修改 docs/state.md，由 root 统一记录全局进度与最终 PR/merge 身份。
