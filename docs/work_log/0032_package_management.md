# 0032：包管理与独立第三方开发

2026-10-25。用户要求规划包管理并修正用户态开发/安装方式。本组仅文档。

新增package_management.md：独立SDK项目、宿主xos_app/客体xpkg候选、ustar/JSON
包与profile、文件归属/精确依赖、P1候选盘离线安装、P2维护会话事务/恢复、P3
仓库与签名。线程T0–T2仍优先，包管理不等待线程/fork/CPython。CLI/schema/格式
细节在P0实施冻结，全部P gate为not_run，不称已安装/已实现。

重写friend_user_program_quickstart.md：发行compile.py/普通main、已有离线桥与
原生GCC/G++流程；删除修改系统程序清单/重建镜像及没有GCC/文件路径/64KiB堆
等过时默认说明。区分旧发行sup>、新Xsh和各SDK能力，未来命令未实现明确标记。
同步主计划v0.8/决策/索引/state，格式等仍属工程建议，不冒充用户逐字段批准。

按入口读取纪律/状态/计划/决策/相关工作记录；核对SDK导出、发行compile.py、
release_smoke、work_disk.py/host FatFs、文件ABI/服务、main入口与许可证。现有
离线桥只支持mkdir/import/export，不覆盖目标，没有整包事务或数据库；单文件
staging也不等于多文件原子提交。TUF官方规范供P3选型，GNU tar规范页抓取超时；
实际格式/schema边界仍需P0核验，未引入外部代码/依赖。

文档格式/引用/一致性检查通过；本轮没有编译、安装、QEMU、客体gate或旧压力
复现，没有新build ID/包。未改发行附件、工作盘、线程或0030源码/cache、localpilot；
未提交推送。最初文档补丁因同文件重复操作校验失败，没有写入，已改为单次写入。
下一组先做P0，公共ABI与线程主端协调；P1在独立候选盘闭环，P2另领维护机制。
本组结束，无剩余编辑占用，没有派出agent或向其他线程发消息。

用户续示补充已核对：0030 PY0a/PY0b为7/7，0033 Shell UTF-8通道U0/U1已验，
文件路径U2尚未完成。Open Adventure为adventure_port_plan.md的原生生成/编译
任务，由用户移植线推进；作为后续包样本，不冒认当前已完成，也不重跑其验收。
