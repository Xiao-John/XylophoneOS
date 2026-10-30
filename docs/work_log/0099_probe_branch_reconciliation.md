# 0099：PR #25共用探针整合

2026-10-29。用户授权基于作者分支修改、不merge上游PR。先合并main 3e5ccd0，再合入
PR #21源码提交c152f7f到本分支以统一共享探针；没有向main合并任何PR。
原#21/#25均保留祖先关系及冻结reports。解决许可证表、builder和runner三处冲突：
许可组件按name合并，QuickJS保留phase2最新登记；runner逐字节采用phase2版本，保留
求值结果、pending/rejected/fulfilled与job排空检查，不退回弱完成断言。

builder保留phase2每次新目录/复制补丁和实际runner/builder/patch/source哈希；--output
兼容phase1旧调用的默认build/modern_apps/quickjs，但默认/显式目录都严格拒绝复用。
没有改现有SDK、私有项目、系统运行时或安全检查；显式私有源码输入仍须另行授权，
本轮未执行该类探针，也未读取localpilot。state保留两组事实，历史“当时无review”只作
历史，不作为当前PR状态。#21与本分支现已共享可整合祖先，避免重复add/add。

实际宿主检查：默认/显式输出已有目录均拒绝且sentinel不变；build外路径拒绝且不创建；
Python语法通过；许可组件名唯一、87项登记artifact哈希通过；phase2 runner原字节保留。
摘要/tmp/xos_pr25_builder_checks.json。文档/ABI及差异检查通过。
未重建QuickJS/新系统或重跑guest，原11/14探针结果保持原输入绑定，当前组合未验；
不能因runner相同就称整合后的全部夹具已执行。后续仅需按最终新组合补对应定向资格，
不用重跑无关压力。推送作者分支由主端统一执行，不自行merge。
