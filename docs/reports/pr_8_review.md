# PR #8 review

2026-10-28。审查对象：[PR #8](https://github.com/Xiao-John/XylophoneOS/pull/8)，
`d1e108d8f31ffcb1ebf43b40a412af933fb074cd`；远端 main 与共同基线均为
`244ac40bbf4e4fb7743c51bc5ece0bd9fec594de`。PR 当前为 Draft。

## 结论

本轮未确认需要阻止合并的缺陷。建议作为受限静态 QtCore 功能移植合入 main；
不由此授予发行、完整 QtCore、QtGui/QPA 或全 POSIX 资格。
这是源码、集成与已有证据审查，不是审查者重新完成客体验收。

## 实现检查

- 新适配位于 `src/ports/qt6/`，无内核、loader、共享 ABI 或服务 op 修改；
  唯一公共运行库工具改动为 threading compile 脚本的 C++ 头文件隔离及搜索顺序。
- 对照固定 Qt 6.8.3 上游相关实现检查 dispatcher、timer、QThread 生命周期、
  QMutex 慢路径和文件适配。wait-word gate 在检查工作队列前消费唤醒位；生产者
  release 置位后唤醒，内核比较零并入队，检查到阻塞之间的通知不会仅靠一次 wake 保存。
  互斥等待使用真实 pthread 条件变量与绝对单调 deadline，没有新增忙等替代机制。
- FD/socket notifier、文件映射、权限/链接及若干路径操作明确拒绝或排除。
  不把这些明确范围限制记为实现缺陷；直接 pthread_exit 退出 Qt worker、取消、
  多源等待及后续图形阶段仍不在此次资格内。

## 集成

`git merge-tree --write-tree origin/main refs/review/pr_8_head` 成功，合并树
`caae63a6b52b33824a137ae8547ea5c95803aee1`。远端 main 可干净合并。

当前本地 HEAD `1945651` 与该 PR 的只读试合并有六处文档冲突：
`docs/Discipline.md`、`docs/acceptance.md`、`docs/contracts/qt_platform.md`、
`docs/plans/qt.md`、`docs/state.md`、`docs/xos_plan.md`。没有源码文本冲突。
本地另有未提交的 DU 设计文档，包含 state/宪法登记更新；本轮保留，未实际合并。
后续整合应同时保留本地 C20–C26、全工作区提交纪律和 DU 设计，以及 PR 的 Qt 事实更新。
这一整合事项不构成 PR 与当前远端 main 的冲突，也不代表新组合已验收。

## 实际执行的检查

从 Git ref 导出隔离源码至 `/tmp/xos_pr_8_review`，不切换或改写现有工作区源码。

| 检查 | 结果 |
|---|---|
| 主证据 PACKAGE_SHA256SUMS | 99 项匹配 |
| 补验证据 PACKAGE_SHA256SUMS | 64 项匹配 |
| qualification 中适配/补丁源码哈希 | 12 项匹配 |
| 主系统 manifest 对 PR 源码 | 565 项匹配，无缺失 |
| threading SDK inputs 对 PR 源码 | 66 项匹配，无缺失 |
| 补验 serial gzip 解码 | 通过 |
| tests/docs_consistency.py | 通过：332 链接、66 syscall、73 历史来源 |
| tests/abi_doc_consistency.py | 通过：12 项当前接口表 |

文档检查在独立临时 index 上使用 PR 的文件清单与本仓库历史；结果位于
`/tmp/xos_pr_8_checks/`。没有独立核验未随 PR 提交的 Qt 归档、SDK 二进制或系统镜像，
也没有重新执行源码解包/补丁重放、Qt 构建、客体功能/回归或压力测试。
已有客体通过结论仍来源于 PR 冻结报告及串口材料，不能表述为本轮复现通过。

`git diff --check` 另报告补丁文件空白上下文行与原样保留的 zlib 许可证末尾空行；
未视为运行缺陷，也未修改上游许可证或补丁上下文。
完整成员许可证审计及静态分发/重链接材料仍为 NOT_RUN，PR 已明确记录。

本轮没有修实现、提交、推送、合并、发布或向 GitHub 发送评论/审批。
