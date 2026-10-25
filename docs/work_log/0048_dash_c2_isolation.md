# 0048：Dash C2隔离执行

2026-10-26，feature/dash-c1-c3，固定上游4c78b27。C1已由3e5f321冻结并通过全部
受影响回归后才开始C2。旧镜像/SDK/证据保留build/dash_c1_frozen与docs/reports。
主负责ABI、libc/Dash、整合和串行构建/QEMU；子agent分别负责kernel三文件、
files/Client三文件、独立测试。没有并发构建/清理，不碰localpilot、日常盘或Release。

选择单线程eager-copy fork，而非spawn/reexec伪装subshell：保留实际AST、函数、
非导出变量/标志、参数与执行位置，代价是全部已映射用户页；不引入COW复制路径。
认证文件会话克隆保号共享offset，子PID所有Client重绑，ACK之前不可运行。
新增sys57–59/file op20与失败原子性见e04_loader_sdk.md。权限不提升，fork depth3。

Dash支持builtin/function/compound pipeline、subshell、$()与backticks，展开会
修改状态的stage先fork；C1纯literal外部stage保持直接并发spawn。pipefail取最右
非0，保留EV_TESTED使set -e测试语境正确。捕获raw stdout上限1MiB，超限明确失败；
RESET/EXITRESET关闭capture、取消/收集job，防止交互错误后遗留all_jobs/子任务。
当前EV_EXIT外部仍spawn+wait，因此forked stage执行外部有额外进程开销，资源不足
明确报错清理；真实exec属于C3，不称已实现。后台/信号trap/here-doc仍拒绝。

## 中间真实结果，尚未冻结Gate

完整初建build0a5482b6c3c8467b（kernel364604B），Dash650d0492…；C2专项首次27项
passed，含低层fork三轮、共享FD>=3偏移/CLOEXEC继承/内存PID/cwd/env、14个宿主
参考语义、32KiB捕获/尾换行/状态、三层嵌套、深度/配额失败、fault、Escape和重复
回收。资源[129832,2,0]。build/dash_c2_attempt1_report.json保留完整输入输出副作用。
单次254MiB真实fork复制ENOMEM与部分复制回滚也passed，外层资源回基线；
build/dash_c2_oom_report.json含持有大分配前后及失败后实际计数，未假定free缩回sbrk。

审查修正：首次新增mkinit钩子用单行块导致生成C编译错误，改为多行块后编译通过；
补EV_TESTED和pipefail，正常客体已验证。随后增加捕获上限与互动超限清理定向用例。
最终完整源码构建、线程SDK拒绝fork及全部受影响旧回归进行中，未先宣告C2 Gate。
C3匿名here-doc、真实exec/身份/FD/失败原子性及实际Make尚未实现，不算passed。
