# E08 受限功能验收结论

2026-10-24（Asia/Shanghai）。**E08-1至E08-6当前约定的受限功能gate完成**。
这是历次已接受证据加本轮C++增量的结论，没有重复旧C/CRT/压力测试，不冒称
最终镜像上的完整旧回归或压力全绿。O11/O12/O13在以下静态子集有真实证据，
并非完整POSIX、完整C++标准库、动态链接、线程、系统重建或编译器自举。

| 证据 | 结论 | 版本与记录 |
|---|---|---|
| E08-1/2/3 | 存储/会话/进程/libc/GNU binutils受限gate已接受 | 0012/0013/0015；S2定向修复0017，历史压力报告原样保留 |
| E08-4 | 原生GCC C，4组/15命令 | 82ffcecab8ccbcce，0020 |
| C编辑持久化增量 | 4检查/18命令，V1→编辑→V2→正常重启V2 | 82ffcecab8ccbcce，0021；测试镜像与manifest已保留 |
| C++早期ABI | 6/6客体通过，容器/string、异常、RTTI、local static、TLS析构、多TU | f40c9a254b5433d7，0022 |
| E08-5 | 原生G++/cc1plus，4组/14命令；两任务TLS隔离、跨归档/TU异常析构、错误路径、源码保护 | 6b7d5cfc3612fdf4，0022 |
| C++编辑持久化增量 | 4检查/18命令，真实多TU/静态库、V1→编辑→V2→正常重启V2，源码/工具hash核对 | 2c3876e640840ff5，0022 |

两个集成runner各自返回passed_partial_language，不会自行决定整个E08完成；本页主端
依据C/C++均通过、前置阶段已接受合并判定E08受限功能范围通过。机器汇总
build/e08_acceptance_report.json保存各报告hash和所测版本；原始报告不改标、不同
版本不混称同一轮全量。最终系统相对原生G++ gate仅增加licenses/components.json
的target库用途登记，327项当前源码hash与manifest一致；实际CRT/库/头与SDK v5
一致，只有SDK build metadata及许可组件表不同。

最终构建2c3876e640840ff5，源码SHA256
2c3876e640840ff556a0aa80e5dfdce000e944c6649839ff41092ca833242e18，
xos.img SHA256 1c2cfa90d65b9a9585ac3d5cef32c8376b1806e65f7502321912b2e15b54454c。
原生G++产物cpp_app.elf 848056字节，SHA256
445724fd060d30da740ce072a35baa4a1497cf6bbc3c0773ff52967b8ee72db0。
最终重启验证的C++产物cpp_app.elf 791368字节，SHA256
22623589bad346e7498980d29ef86a02d0d81821134d2befb6aa82acb7661970。
逐命令页/任务/完成记录恢复[130342,2,0]；native两个TLS worker PID35/36已正常wait回收。
原生阶段日志观察到最大单次子任务回收20501页，约80MiB；这只是退出时回收量，
不能冒充任务或全系统真实高水位。Seed/sysroot安装白名单累计185903068字节，
也不是真正磁盘峰值。真实高水位、长soak与后续压力由专人负责，未在本轮测量。

本轮实际失败已修：GNU TLS回退与v5入口重复定义；新g++也缺lrealpath返回值。
均在独立派生目录修复并绑定hash，原A/B与旧SDK不覆盖，完整过程和可复现命令见
work_log/0022_cpp_seed_acceptance.md、e08_cpp_seed.md。没有通过关闭异常/RTTI/TLS
回避验收；host工具自己的无异常/RTTI库和目标应用库严格分开。

当前边界：512MiB单核TCG、8任务、每任务65536页、16文件打开/session、32个全局
FatFs锁、ASCII路径、静态local-exec TLS/单用户线程；固定/sysroot直接GNU ld profile。
collect2、LTO/插件、任意-pipe流水线、动态TLS/DTV/DSO卸载和任意掉电保证不在验收。
GNU运行库例外/原许可保留，7份SDK声明及已登记组件hash检查通过；静态归档逐成员
许可证追溯和公开对应源码分发包核对未完成。未提交/推送/读取凭据或操作日常盘。

下一步按计划进入E09交付与朋友真实试用，或由用户安排已纳入计划的后续支线；
本轮结束，不自动开始Qt、系统重建或自举。
