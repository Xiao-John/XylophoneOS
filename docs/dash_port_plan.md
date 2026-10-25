# dash继续移植：先让日常开发顺畅

2026-10-25。A、B0、B1和B2已完成受限gate，见shell_subset.md、0028与0042；
Xsh保留原生入口。C尚未实现，不将上游有该语法等同于XOS已支持。

## 顺序

| 批次 | 工作 | 完成证据 |
|---|---|---|
| B0 启动契约 | 固定普通启动、driver构造权和受限委派；定义可观测退出/故障/取消，保留Xsh救援 | **passed（0028）**：dash真实启动gcc/g++及cc1/cc1plus/as/ld；无权委派退126且无产物，资源回收 |
| B1 简单开发脚本 | 在保留上游语法前提下开放并验收实际用到的case、函数、dot、参数展开等；补缺失小工具 | **passed（0028）**：dash内故意编译失败、cp替换源码、C/C++重译执行；sbase五工具过客体gate |
| B2 文件描述符 | 真实打开实例转交、共享偏移/状态、dup/close/CLOEXEC、顺序文件动作与失败回滚 | **passed（0042）**：>、>>、<、2>、2>&1次序、builtin恢复、失败继续、嵌套Escape及资源回收 |
| C1 管道与等待 | 阻塞或可靠可等待pipe、并发启动所有段、子任务完成查询与前台输入路由 | **passed（0047）**：4段131109字节全比较、EOF/EPIPE、异常、配额/取消与资源回收；C2隔离另验 |
| C2 隔离执行 | 选择fork或自重执行/状态传递，开放pipeline内建/函数、子Shell与命令替换 | **passed（0048）**：真实fork/文件会话克隆、14参考语义、1MiB捕获边界、深度/ENOMEM/清理 |
| C3 脚本兼容收口 | here-document、exec替换、实际所需信号/终端语义；引入Make等真实消费端 | 选定真实项目的构建脚本/Make配方在客体运行，失败诊断可复现 |

建议先B0+B1取得日常开发收益，再完成B2；C1/C2分开验收。历史/补全可作为小支线，
不阻塞编译和脚本；复杂交互投资仍优先留给xsh。没有经过实际实现不承诺小时ETA。

## B0：已实现的受限委派

sys_process_delegate接受最大3层的显式深度。supervisor可设置受限深度；
普通持权任务只能修改自己尚未启动的直接子任务，且新深度必须严格小于自身。
旧sys_process_grant仍仅允许supervisor赋予一层直接构造权。Xsh对裸`dash`启动
显式给深度2；dash在用户态固定GNU driver profile中给gcc/g++深度1，其子工具不能再委派。
内核不识别文件名、PATH或GCC。直接`exec-driver dash`仍只有旧一层权利，尝试委派会
明确返回`process_error_delegation`/EPERM。

当前gate已覆盖旧直接driver兼容、无权委派拒绝/回滚、受权C/C++子工具链与退出回收。
配额耗尽、父进程取消正在编译的多层链和collect2仍非本组已验范围。

## B1：已实现的简单开发脚本

dash保留上游解析、引用、展开和控制流，admission新增递归放行case/NCLIST、
函数定义与dot读入后的脚本；参数展开使用上游实现。管道、子Shell、后台、
命令替换和重定向仍在执行前拒绝。

外部工具固定sbase commit c546c3a5724c81cee9a11d816a38ccdf17472129，仅移植
cat/cp/mkdir/mv/rm的窄行为：普通文件、同卷改名、mkdir -p与非递归rm。无权限位保留、
符号链接、递归复制/删除、跨文件系统fallback或目标覆盖承诺。

当前已通过的基本形式：

```sh
cd /src/demo
/usr/bin/x86_64-elf-gcc --sysroot=/sysroot -c main.c -o /out/main.o &&
/usr/bin/x86_64-elf-gcc --sysroot=/sysroot /out/main.o -o /out/demo.elf &&
/out/demo.elf
```

现可把B2已验的日志重定向加入正式示例。所有命令应可通过PATH自然调用，同时继续
提供明确的文件/启动失败诊断，不能借用Xsh的特殊exec语义解释POSIX exec。

## B2：已通过，不能用重开路径模拟继承

当前孩子按路径重新打开文件stdio，独立游标无法满足2>&1、共享偏移、重定向顺序。
应在用户态文件服务中管理可引用的打开实例，跨进程导入/转交绑定实际调用者和
目标接收者，引用计数随close/退出/kill回收。内核只转交可信句柄/身份机制。
同时移除libc以本地缓存偏移假定独占文件游标的行为，使SEEK_CUR等由真实共享
打开实例决定。FD_CLOEXEC属于描述符，O_APPEND等属于打开实例，分别验收。

posix_spawn文件动作按顺序执行；失败不能操作未指定的文件、泄露句柄或留下可运行
半成品。按POSIX先执行的重定向可能已产生合法副作用，不承诺事务回滚。父Shell
临时重定向结束必须恢复，即使builtin或展开报错。
顺序文件RPC目前依赖每任务会话；并发、超时和多Client请求ID分配在这一阶段一起
明确，不能把当前同步路径推广成线程安全或任意迟到响应恢复保证。

## C：先可靠流，再隔离环境

pipe仍为4KiB有界缓冲，A运行库可返回EAGAIN；通用工具不能靠Shell忙循环猜测。
先补阻塞/等待、关闭引用与子任务并发启动。先只验外部程序流水线，再加入内建/
函数段；后者必须有隔离环境，不能在父Shell直接执行并污染其变量/cwd。

spawn继续优先，但不预先否定fork。自重执行要明确变量、函数、位置参数、打开fd
和退出状态如何传递；fork则要补地址空间/句柄/生命周期，必要时先做正确的复制版
再评估COW。以真实兼容需求和复杂度选择，不以保持“无fork”本身为目标。

exec替换涉及PID与进程身份，spawn+wait不是等价替代；信号、作业控制和trap按需要
另做机制，不引入永远成功的stub。用户可以从Xsh恢复故障Shell。

## 验收方法

POSIX支持范围内，与宿主参考sh对照参数字节、状态、stdout/stderr和文件副作用；
OS相关机制必须有XOS客体证据。每批保留已有A gate；不重跑无关旧压力。
资源基线按构建记录，增加代码/服务的固定开销与逐轮增长分开报告。
标准依据：https://pubs.opengroup.org/onlinepubs/9799919799/utilities/V3_chap02.html 。
