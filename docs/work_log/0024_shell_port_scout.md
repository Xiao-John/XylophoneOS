# 0024：Shell 移植勘查

2026-10-25，用户要求找到合适且能快速落地的上游 Shell 路线。
主agent负责全部勘查，没有新启动子agent；仅占用本记录、state.md 和
shell_port_scout.md。其他压力侧文件保持原样，未读取 localpilot。

完成：取得 dash 0.5.13.5 和 BusyBox 1.37.0 原包；dash 四个关键文件与 kernel
镜像 tag 逐字节一致。分析普通命令/管道/子 Shell/命令替换路径，核对现有
spawn、wait、fd、pipe 和构造权。建议 dash + 局部 spawn 后端，先简单命令再
重定向/编译器，最后管道及隔离环境。详见 docs/shell_port_scout.md。

实际探测位于 .cache/xos_seed/shell_scout/。以冻结发行 SDK、交叉 GCC16.2.0、
宿主 clang 构建生成器，dash configure 成功；JOBS=0 的 make -k -j2 返回2，
14个顶层目标对象生成，停在声明/头文件及兼容缺口。没有完整链接、宿主 Shell
行为测试或 XOS 客体运行；不标记移植成功。hush 只作源码分析，未目标编译。
没有修改内核/运行库/上游源码，没有重跑已有测试或改变发行附件/标签。

关键输入与输出摘要、精确配置、失败日志在报告对应章节及缓存 report.json；
持久文档保存原包SHA256、已暴露缺口和下一步，清理缓存后也可继续实施。
候选尚未成为系统/SDK依赖；dash 混合许可材料和 BusyBox GPLv2-only 静态组合
问题已记录，未变更既有授权。

下一步按报告 A 批次建立独立 ports/dash 原包锁/补丁/构建入口，取得真实可运行
简单 Shell；B/C另验。当前勘查已结束，没有剩余编辑占用。未提交/推送。
