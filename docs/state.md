# XOS 当前状态

更新时间：2026-10-27（Asia/Shanghai）。main已对齐PR #3 squash基线afcfe47；
后续本地工作通过codex/post_pr_3_integration分支PR交付，未更新发布资产。旧状态全文归档到[cb26f7b快照](history/state_cb26f7b.md)，
其中阶段编号相同的记录按文件名识别，不从历史措辞推断当前状态。

## 当前已交付与证据

- **发行**：0.0.1-1026已发布，tag/source为db5b46c，build7a4668477d7323de；
  实际发行包smoke 11/11，7份许可材料检查。images/SDK/source/校验表/manifest的
  回执见[发布记录](releases/release_0_0_1_1026.json)。新工作盘不预装dash，ISO携带
  并在首次启动安装；这些资产没有因为本次修复重新打包。
- **线程**：T0–T2已通过[冻结资格](reports/threading_20261025/qualification.json)；
  T3-PY、PY2有各自专项证据（0043/0046），T3-QT/SMP未运行。旧SDK/线程资格不改绑当前源码。
- **dash**：B2已由0042验收；PR #2已合并C1–C3受限功能，冻结资格见
  [C3](reports/dash_c3_20261026/qualification.json)，build2f7160b7d6633ee6。
  pipeline、eager-copy fork、命令替换、HereDoc/exec/Make已有阶段证据，不等于完整POSIX。
- **显示**：PR #3原分支E14/G02受限验收见[显示后端](display_backend.md)和原始冻结报告；
  本地0059已整合其实现，显示编号改为65/66，当前组合的定向证据单独记录，不替换原G02资格。
- **ISO**：0047已验真实5.6 MiB kernel和2.1 MiB payload；预算kernel文件8 MiB、
  内存16 MiB、payload32 MiB。容量probe只用于验收，不作为发行载荷。
- **CPython**：PY3 A1–A3受限gate及B1系统熵已有证据，详见0049_cpython与0052。
  B1独立build46cb97b1555633f1，RDRAND/不支持两种配置均验；信任CPU/hypervisor，
  不承诺RDSEED/virtio-rng。B2–B4已按当前共享ABI/SDK和单一CPython构建完成客体验收，
  见0058；不因此更新1026发布资产。
- **xypm**：P0/P1、P2-1门控已验。P2-2原生verify/plan是实现初版，冻结B2 SDK
  打包状态packed_guest_not_run；guest/畸形输入差分及完整ELF契约未完成，见[0051](work_log/0051_xypm_p2_verify_plan.md)。
  P2-3持久journal/启动恢复与P2-4客体写命令尚未开始，不能由只读计划或内存屏障替代。

## 0059完成：PR #3本地兼容整合

PR f84745a的78路径已整合到未提交工作树；5个文本冲突已解决，熵63/墙钟64保留，
显示使用65/66，SDK生成器与ABI文档同步。0054审计、0058 CPython和其他本地改动保留。
最终独立build **76a2e4380f64fb2e**（build/pr_3_compat/system_final），7组新组合客体、
12项ABI表/编号唯一性、boot_info宿主边界、11项SDK绑定与7份许可材料通过；未重跑旧压力。
0059当时保留未提交工作树；0060已在用户squash #3后核对远端并对齐基线，转入独立PR分支。
具体旧失败及范围见[0059](work_log/0059_pr_3_local_compat.md)，对齐与交付见
[0060](work_log/0060_pr_3_squash_alignment.md)。原cb26f7b保存在codex/backup_pre_pr_3_cb26f7b。
本组源码/构建占用已释放；今后新任务按Discipline通过独立分支和PR交付。

## CPython PY3 B段完成

B1安全熵见0052；B2墙钟/时区、B3 SQLite和B4 bzip2/liblzma/zstd见
[0058工作记录](work_log/0058_cpython_py3_b_segment.md)。三项使用CPython fingerprint
`11c39c52e451a9499450`、线程/C++ SDK manifest
`22960edc51be4a8a8bc0726c2179c2200b02509d49bc2aceb3640aa463d60c13`；共享系统镜像和
客体最终回执以0058记录为准。B2覆盖RTC UTC墙钟、POSIX DST和ZoneInfo/tzdata；B3覆盖
事务、约束/忙错误、损坏输入及sync/重启重开；B4覆盖三种压缩流、损坏/截断和输出限额。

边界：墙钟由PC RTC启动快照加PIT单调增量形成，QEMU测试固定UTC；暂停/挂起虚拟机后
没有独立虚拟RTC刷新承诺。SQLite使用单进程、单个可写连接、rollback journal，不含WAL
和跨进程锁。压缩只验所列模块的静态构建与客体API，不表示所有格式或归档命令已移植。
不触碰dash，不重打包/更新1026发行资产，不提交。当前工作树另含0054审计修复及其他本地更改，
均保留原样。

## 0056完成：POSIX子集文档

已建立[posix_subset_contract.md](posix_subset_contract.md)与[posix_roadmap.md](posix_roadmap.md)，
参照POSIX.1-2024，明确当前受限基线、标准选项待核对项、微内核责任和PX阶段验收。
PX0仅文档完成，PX1及以后未实施；建议下一项是PX4-A VMA/匿名映射设计包，不视为已开工。
墙钟已由0058专项收口；完整时间接口仍待PX6。xsh默认入口不变；COW不是POSIX必需条件。
本会话文档占用已释放，未改实现/ABI、未构建或重跑旧测试；见[0056](work_log/0056_posix_subset_contract.md)。

## 0054完成：audit_report_01修正

- A01：files恢复将明确缺失与I/O失败分开，预检恢复材料后才清理；检查关闭、删除、
  重命名和同步结果。清理失败保持io，journal延后删除；最终删除后flush失败时尽力
  恢复marker，仍保持失败关闭，不承诺坏盘/任意断电时一定能重建日志。
- A02：当前维护ABI为sys62/file op23、24；sys54与op20–22保留给PR #2。
  [SDK当前表](e04_loader_sdk.md)由轻量测试核对，旧报告不机械替换。
- A03：计划、当前入口、发行后续页和0050历史待办已同步；历史状态保留在快照与工作记录。
- A04：未来发行按系统manifest核对SDK完整文件/目录/摘要、build/ABI/配置，固定C++
  运行库来源；拒绝旧残留staging，记录输入/成品SDK树，资格报告再核对同一绑定。
  不因此认定已发布1026有错配；旧资产/回执保持原样。

最终独立build **e78fbff3985357f3**，`build/audit_01/system`，kernel385084字节；
xos.img SHA256 `44f1551140474c60bbe6478604a379e6e8fc9d4106de48e910c0c9b0295a80bf`。
21项宿主真实FatFs API故障/对照、5项客体启动恢复、9项当前维护门控、11组SDK绑定、
8个当前ABI表项与7份许可材料检查通过；客体资源[130337,2,0]稳定。

旧355fecd维护报告保持原来来源，当前维护证据使用新冻结系统/SDK/探针，未改绑旧报告。
本批无剩余编辑/构建占用，源码/产物/测试摘要及未运行项见[0054](work_log/0054_audit_01_fixes.md)
和`build/audit_01/final_receipt.json`。未跑旧全量/压力、掉电或撕裂扇区测试；没有推送。

## 0057完成：PR #3冲突检查

检查PR头f84745a与本地main cb26f7b及当前工作树：远端main可合并，但当前开发线存在
显示sys63/64与熵63/墙钟64的语义冲突，另有5个文本冲突文件；不宜原样整合。
该审查指出的冲突现由0059在本地修复；0057审查当时未改实现或合并，
未重跑已有测试、未提交/推送。具体范围和证据见[0057](work_log/0057_pr_3_conflict_review.md)。

## 接手与下一步

先读Discipline、本页、xos_plan与相关工作记录。架构方向继续以C类决定为准，P/O/D
不提升为已实现承诺。新任务须登记范围；共享build/不得并发构建/清理，私有目录
保存本轮证据。localpilot独立，不进入XOS扫描/构建/清理。

xypm接手先补P2-2共享有效/畸形包和数据库夹具与客体gate，再按计划推进恢复。
Qt/显示backend、VMA/COW、完整POSIX、SMP/UEFI分别规划，不因本批审计修复擅自开工。

## PR #3分支原始交付摘要（冻结输入）

## 0051：E14 / G02 完成（2026-10-26）

独立分支`feature/display-backend-e14`，上游main基线`5b4e5e1`；源码`23a3698`，
最终build `01c8b149ecc0e4cf`。BIOS VBE 800×600 XRGB8888/stride3200真实像素、
PS/2 IRQ1/12、受保护用户态display服务及SDK、原生木琴演示已实现。
G02 19组通过（含23项显示检查、双线程/真实OOM/异常/回收/三启动/无显卡）；
Dash/Make/CPython/C++线程5组兼容通过，原有9个回归入口通过，详情看冻结报告。
启动后资源基线[130323,2,0]，服务停机/客户端异常后准确恢复。

接口与复现见[display_backend.md](display_backend.md)，正式证据见
[reports/display_e14_20261026/qualification.json](reports/display_e14_20261026/qualification.json)，
过程/失败记录见[0051](work_log/0051_display_backend_e14.md)。仅QEMU11.1.2/
pc-i440fx-10.0/TCG/单核512MiB验证；640×480回退、真机、SMP、长时压力、Qt均未验。
不包含Qt编译/GPU/窗口管理器。其他工作区、日常盘与旧Release保持原状。
本组编辑/构建占用已解除；后文保留历史状态，不把旧“正在进行”当本组占用。
