# 0029：CPython 移植规划

2026-10-25。用户根据朋友投票要求先规划 CPython，实际移植另有用户态 agent。
本轮只占用 cpython_port_plan.md、本记录和 state.md 自有小节；0028 dash 的
实现、构建和验收继续独立，没有占用其源码或共享构建目录。

## 交付

新增 docs/cpython_port_plan.md：建议 3.14 维护分支，先固定 SDK/源码并做 PY0a
依赖探针，再静态单线程 GIL 解释器 -c、脚本/import、传统 REPL 与文件存档。
PY0–PY2 后即可收一次 PY4 分发，PY3 时间/熵/压缩/包/进程等按真实底座扩展。
它细化 E12/用户态菜单，不更改已确认架构、不替换 Xsh 或要求 dash 先完成。
版本/配置属于建议，不冒认已移植，也未写入计划正文为新的已确认 C 决策。

## 勘查依据与限制

读取开发纪律、state、xos_plan、decisions、0025/0027、SDK/Shell 说明、许可和
用户态菜单；核对当前 libc read/gettimeofday、进程页/栈/TLS 限额等实际源码。
当前共享 read 代码已经变化，交接中特别要求使用 0028 冻结 SDK 探测，不沿用
早期“空闲读为零”的假设。保留 %zu/strlen 故障作为待定位线索，不断言根因。

查阅 Python 官方下载/3.14 构建、命令行、许可文档，以及 v3.14.0 的线程、锁、
parking lot、bootstrap、时间、哈希源码。官网列出 3.14.9；内部实现勘查实际是
v3.14.0，不能冒认已审计候选补丁版本。少量源码下载仅在
.cache/xos_seed/cpython_plan/；未冻结 CPython 源码包或生成构建清单。
单线程后端包含无操作 mutex/condition，必须审计内部等待路径，不全球伪造 pthread。
普通 Unix _PyTime_Init 本身不要求墙钟，其他调用路径和 time 功能仍需验证。

## 验证状态和接手

本轮仅文档/源码勘查；没有 CPython 编译、链接、XOS 客体测试或旧压力复现，
没有新系统 build ID。未改发布镜像、日常盘、localpilot，也没有提交/推送。
检查文档引用/文件存在和本轮 diff；不以此替代任何 PY0 gate。
下一位移植 agent 按计划“先 PY0a，再 PY0b”执行，开工先重新登记排他范围，
获取冻结 SDK 后提交真实缺口探针，由主端决定公共机制补充。
本组规划完成，无剩余编辑占用。
