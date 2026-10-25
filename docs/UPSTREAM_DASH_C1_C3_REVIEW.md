# Dash C1–C3 审查材料

目标：Xiao-John/XylophoneOS `integration/2026-10-25`，固定基线
`4c78b27c8f07eeb69145d85786660689fe2db9df`。提交只在fork的
`feature/dash-c1-c3`，不直接合并或修改上游/Release。初始006d870/0a0fbed WIP保留。

## 建议PR标题

dash: complete bounded C1–C3 pipelines, isolated execution and scripts

## 问题与行为

原B2只有同步外部命令与0–2重定向，pipe EAGAIN不能支撑可靠流水线，subshell/
命令替换/here-doc/真正exec与Make消费端均缺失。本分支补充实际机制并分别验收：

- C1：4KiB pipe等待与close唤醒、并发启动/收集最多4段、启动失败与配额清理、
  构造期间及运行期Escape组取消；当前SDK小write用明确flag保证<=4KiB原子性，
  原raw短写ABI保持，禁止用忙轮询冒充pipe阻塞。
- C2：单线程完整复制fork，认证files会话克隆后才能运行；函数/非导出变量/参数/
  cwd/所有FD来自实际执行环境，非spawn伪subshell。支持pipeline builtin/function、
  subshell、$()/backticks、尾换行/状态、1MiB捕获上限、深度/ENOMEM/取消回收。
- C3：匿名打开实例填充/只读seal/最后引用删除支持大HereDoc；exec单一提交保持
  PID/TID与FD身份、切换后回收旧VM；当前CRT能力标记和startup v3恢复32FD/别名/
  CLOEXEC。真实sbase Make固定c546c3a，-B串行显式依赖profile，在客体构建真实
  C/C++项目并由客体GCC/G++自构建Make后继续消费项目。

## 源码审查顺序

1. f19c02d / ed65bf8：C1实现与线程/FD在途lease测试；3e5f321冻结C1资格。
2. ea3d2d0：fork准备/认证ACK/提交、files引用与Dash隔离；6f82d70冻结C2资格。
3. a455f53：exec stage/commit、v3 FD恢复、匿名HereDoc、Make端口与专项。
4. 6e57afd / 3079484：小写等待完整空间，并用显式flag保留原raw ABI兼容性。
5. 最终资格提交只整理真实回执/说明，不自动更新正式Release或合并上游。

重点源码：共享process/file ABI；tasks.cpp生命周期/权限/队列；paging.cpp复制；
newlib_syscalls.cpp的FD group/exec失败路径；loader/load.cpp持文件校验/构造；
files.cpp克隆/匿名实例/最后close；Dash 0002/0003补丁与后端；Make固定源码及补丁。

## 验证入口与证据

C1：`docs/reports/dash_c1_20261026/qualification.json`，build f62f20ef40b19677。
C2：`docs/reports/dash_c2_20261026/qualification.json`，build85df2bcabbd6ace9。
C3最终：`docs/reports/dash_c3_20261026/qualification.json`，build2f7160b7d6633ee6，
实现源码e729dc6；22个最终串行入口全部退出0，C3 66/exec16/atomic7专项通过。
0047–0049保留选择、实际失败与修复、源码/SDK/镜像哈希和not_run边界。
本机完整ELF、SDK、原始日志与测试输入保留build/和各独立冻结目录。

专项入口：tests/dash_c1_smoke.py、dash_c1_threads_smoke.py、dash_c1_pthread_smoke.py、
pipe_atomic_smoke.py、dash_c2_smoke.py、dash_c3_exec_smoke.py、dash_c3_smoke.py。
每份报告包含实际QEMU命令、工具版本/SHA、输入/输出/状态/副作用与资源计数。
最终受影响Dash A/B0/B1/B2、线程/C++、进程/文件/持久化、native GCC/G++、
CPython T3-PY、许可材料、ISO file-kernel与Dash安装回归在同一快照串行执行。

## 支持范围与迁移

新增sys54–61，file wire仍v2并追加op20–22；不要在其他集成分支重用这些编号。
旧console spawn/启动v1/v2继续兼容；文件stdio要求可确认的当前CRT能力，
未知/旧目标明确ENOTSUP而不丢输出；显式exec要求匹配的当前CRT/linker/libxos与
`.xos.exec`声明，未标记旧静态GCC/CPython明确ENOTSUP。普通外部命令不被冒称exec。

固定8进程、每进程32FD、4pipeline段、fork depth3、1MiB命令替换、startup总16KiB；
spawn单串255、exec单串4095，容量不足明确失败。线程SDK拒绝fork/exec。后台、
异步POSIX信号、trap/jobs等作业控制、SMP、Qt和完整POSIX仍不承诺。

Make必须-B，不提供真实mtime增量、-j、推导/GNU扩展、-q/-t/-r、$?或+recipe。
137保留为强制终止（不能被-i吞掉），partial outputs保留并诊断；不是完整GNU Make。
匿名文件正常close/kill清理，I/O失败延迟重试；不删除未知跨崩溃遗留。

xypm冻结SDK tree白名单未擅自登记新SDK；CPython仍不启用fork配置，Qt需要独立
后续资格。ISO仍沿用512KiB kernel/1MiB payload边界；Dash保留debug ELF，安装用
验证过相同entry/PT_LOAD/PT_TLS字节的strip-debug runtime，未扩容量或改旧附件。

## 审查与合并

本材料用于维护者审查；不代表完整POSIX、跨ISA启动或正式Release就绪。
未经维护者批准不合并，不能把本实验分支状态直接覆盖其他维护线的资格结论。
