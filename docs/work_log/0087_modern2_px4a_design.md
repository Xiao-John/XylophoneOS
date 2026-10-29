# PX4-A 匿名VMA：调用点审计与独立ABI认领

2026-10-29。`codex/px4a-vma-claim` 从同步后的 upstream `aaec2e9` 建立。
仅[设计契约](../contracts/anonymous_vm.md)与67的claimed提案，不实现新内核入口。
具体[报告/输入](../reports/modern2_px4a_20261029/README.md)与
[命令回执](../reports/modern2_px4a_20261029/validation.json)保留可复查证据。

- 已核物理分配、页表、用户指针、等待pin、loader/fork/exec/退出及V8固定调用点。
- 关键发现：旧copy/destroy仅枚举1GiB窗口；NONE持页不能按present推所有权；
  pin还含process/join输出；V8大地址与低4GiB安全前置仍缺。
- 提议sys_vm67的64字节wire、操作/错误、匿名地址图/预算、原子回滚、分批内核续体、
  strict W^X/NX与V1–V7验收；线程SDK原fork/exec拒绝保留，共享内存/动态链接另期。
- 修改限定文档/state/PX/ABI认领和源码审计工具；未改运行代码、普通/线程SDK、
  原始phase1/N1/浏览器/LocalPilot/日常安装或其他工作区。
- 文档/ABI/whitespace及固定源哈希检查通过；V8一额外文件获取SSL EOF、Issue8页面403
  保留为失败。没有新系统构建、真实ELF或QEMU执行，客体及所有运行门槛NOT_RUN。

公共实现 **BLOCKED**：维护者审查并合入认领后另开功能PR，不自批/合并。
下一负责人独占契约列明内核/SDK公共文件，先完成VMA/页表生命周期，再真实验收；
不把本设计或旧Qt/线程通过记录当成Chromium/V8/Web/App/发行资格。

## 同步PR #24（仅文档，不改原冻结审计）

2026-10-29，将 upstream `169f51e` 合入本分支，保留PR #24原作者和两个文档变更。
读宪法v1.3及0086修正记录后，匿名VM契约明确只消费时间中断唯一写入的公共单调
时基；VM不建tick/TSC/宿主时钟/EOI计时，32页续体批次不是时钟。无deadline字段
的新请求不借机新增计时ABI；未来等待/deadline先登记且必须同源。
C29公共时基整改仍独立，未完成则相关VM等待验收BLOCKED；设备授权遵守C28且不纳入VM。
旧 `modern2_px4a_20261029/` 源码审计与原validation保持逐字节不变，新文档检查收据
见[同步验证](../reports/modern2_px4a_c29_20261029/validation.json)。仅运行docs/ABI/空白检查，
没有新镜像、ELF、QEMU、时基或VM实现/运行资格，67仍claimed，PR #23仍draft待审。
