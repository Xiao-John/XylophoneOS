# 最终 GNU 公共运行库的 R2 代际资格

在统一源 `299ea47cc991fb781e8671c41213a02c169f4130` 与最终 native build
`faad61f4f20be0f7` 上，使用全新 GNU v5 / C5 和独立批准的 CSDK v4 完成
R2 三轮。每轮七项检查及四次真实 GNU C 启动，合计 21/21、12 次启动通过，
资源全部精确恢复 `129778 / 2 / 0`。

launcher 与 probe 从完整同 revision 源重新构建，没有 overlay。批准根是
C5 实际 generation 1、同 ELF 不同 main 路径的 generation 2，以及故意不
安装 main 的 generation 3。一个 controller 连续完成 0→1→0、保留旧 pin、
stale sequence 拒绝、失败激活保留旧代、撤销非活动代和撤销活动代。

实际命令使用 `build_dynamic_launcher.py`、`build_dynamic_generation_probe.py`
和 `dynamic_generation_guest.py --repeat 3`；调用中显式给出 immutable system
source、独立 SDK manifest/tree 双锚和 producer Git revision。全部构建和
guest 在 Preview 2 中完成。完整参数、工具、产物与串口见
[最终 R2 报告](../reports/dynamic_generation_final_20261128/README.md)。

后验核对包括 8,837 个完整源文件、71 个 launcher/program/runner 输入、375
个唯一 GNU producer 源，以及实际九项 GNU 产物。C5 native SDK snapshot 的
239 文件、12 目录、archive provenance 与真正 faad SDK 全量一致，分别记录
两种 inventory 摘要算法。生产源码及历史资格未改写。

本轮没有 guest 失败，没有降低 deadline 或验证标准；GNU 新 READY 路径和
新 native ABI 的真实新字节已运行。volatile 单 controller 范围至此通过，
持久策略、跨后代撤销与进程树预算继续留 P1。R1 原始 1024 四冷启动由主任务
合格候选就绪后单独执行；state/计划与 PR 合并由主任务统一管理。
