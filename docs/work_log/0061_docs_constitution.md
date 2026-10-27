# 0061：宪法、ABI登记与文档压缩

2026-10-27。基线PR #4 squash a265061；分支codex/docs_constitution。

## 已完成

- xos_plan.md由790行改为原则/当前登记两部分；保留C01–C17方向（C12被C13替代），
  加入用户确认的原则/事实分离及PR交付。原则裁定实现违规，过期登记据源码/证据更新，
  P/O/D不自动升格；阶段/验收状态从叙事中分离到state与acceptance。
- contracts/abi_registry.md逐项登记现有sys1–66；0保留，67–79内存、80–95等待/信号/
  进程、96–111显示扩展预留，112起未分配。只有预留段，没有新增syscall实现或假能力。
  claimed预认领与allocated源码分配分开；实现时拆分号段，不允许同段自由抢next。
- contracts/qt_platform.md划分Qt移植/通用等待/内存/显示/线程/文件责任、最小缺口探针、
  公共头/manifest整合与独立gate，不预造Qt内核ABI或派出agent。
- 16份当前文档归入contracts/plans/implementation，保留核心架构/SDK/用户命令稳定入口。
  49份旧工作记录及3份旧勘查/快照合并为6个实现主题摘要；另压缩design/decisions与旧AI
  附录。原稿/被更新说明共73份在history/source_index.json登记原提交/路径/SHA256。
- 更新README、Discipline、当前状态、相关端口README及本地AGENTS入口；AGENTS原本被
  /AGENTS.md规则忽略，保持本地文件，不强行加入版本库。仓库正式流程以Discipline为准。
- 去掉旧“无线程/无墙钟/无Make”等冒充当前状态的条目；ELF/SDK修正初版栈说明为当前
  128KiB栈+16KiB startup，细节仍由共享头/专项契约约束。没有修改运行时代码/ABI。

## 验证与证据

```text
python3 tests/docs_consistency.py --output-dir build/docs_constitution
python3 tests/abi_doc_consistency.py --output-dir build/docs_constitution
git diff --check
```

文档检查核当前链接/锚点、全66个syscall与源码、号段无重叠/抢占、claimed不重号/不越界，
并用git show逐项核73份原文摘要与目标锚点。浅克隆运行来源检查前须取回source_commit，
普通系统构建不依赖该历史检查。12个原SDK当前表项保持一致。

内存注入检查：重号、未获分配的reserved接口被拒绝；claimed67合法，claimed63与112拒绝。
130个冻结reports与正式release文件逐字节SHA256未变，源码/失败/资格回执没有改绑。
本轮只运行上述宿主文档/登记检查，没有重建系统、Qt或SDK，没有重跑客体/旧压力。
新增检查脚本会改变未来源码manifest输入，不能把旧build76a2e438的资格称为本分支重验。

非冻结Markdown由136份/10610行减少到95份/5253行（约50.5%行数缩减）。
统计和报告保存在build/docs_constitution/{before.json,docs_report.json,verification.json}；
旧全文通过已登记Git对象恢复，无需复制第二份叙事归档。未删除build/cache或发行附件。

## 交接

本组文档占用解除，以独立PR交付。其他人待登记合入后从新main领取具体claimed条目；
Qt版本/G01、VMA/PX4-A与通用等待仍未实施。新增任务仍先登记范围，新日志收口后合并到
主题history，不再次累积过期“正在进行”。未来原则变化须用户明确确认，登记更新不能豁免。
