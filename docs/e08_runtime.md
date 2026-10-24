# E08-2：工具运行时

2026-10-24，受限客体gate与最终集成回归已通过，构建5276ff16bb6470b0。证据见
work_log/0013_e08_2_runtime.md；不是完整 POSIX 声明。

0017追加修复：普通open的libc偏移从0开始，O_APPEND从EOF开始，与文件服务一致。
修复前错误地把所有已有文件偏移记成大小，干扰SEEK_CUR和stdio缓冲定位，导致
S2多成员archive最终链接失败。定向回归与新Seed见work_log/0017_archive_position_fix.md。

## 进程、地址空间与启动

ELF 校验/逐页装载仍在用户态。静态 ELF 不得占用堆保留区
`[0x60000000,0x70000000)`；sys_heap_break=29 查询/增长/缩回当前任务堆，
按需分配 RW/NX 物理页，失败撤销本次新增页。任务65536页上限包含栈与堆。
32页可用栈位于 `[0x7ffdc000,0x7fffc000)`，下方一页guard不映射；
上方4页startup存argv/env/cwd与stdio描述，初始RSP在startup下方。

startup_info保留48字节v1前缀，旧SDK入口继续可用。v2扩展位于偏移64，
定义在 `src/user/include/xos/spawn.hpp`；最多64项argv、64项env，每串255字节，
全部指针表和字符串必须放进4页，超限拒绝。CRT提供窄SDK、libc SDK及标准
C main三种入口；libc入口初始化会话/fd/env/cwd，main返回经exit清理stdio。

supervisor的 `exec-driver <path> [args...]` 通过sys28显式赋予直接子任务
构造权。普通exec-file/spawn-file不授予；授权不向孙任务继承，所有构造
仍检查owner与building状态。driver可用posix_spawn启动普通子工具并waitpid，
退出/故障会清理其未收集子任务。没有fork/vfork、信号、adoption或服务重启。

## 文件与stdio

newlib适配层提供32个fd槽，文件对象经每任务可信IPC会话连接files服务。
open/create/exclusive/truncate/append、read/write、seek、stat/fstat、unlink、
rename、mkdir、目录遍历、临时文件及cwd相对路径归一化使用真实文件操作。
files服务仍限制每会话16个打开、全局32个FatFs锁（0020因真实GCC链接容量缺口调整）；fd槽数量不增加后端容量。
close与任务退出回收，短读/短写/EOF/errno保持真实。
stat/fstat使用真实SFN目录项映射身份；保留newlib的16位ino_t ABI，root=1，
最多65534个非root身份，删除编号不复用，耗尽明确失败。rename/保存保持身份，
身份只保证当前服务生命周期，不承诺跨重启inode编号相同。

sys30–34提供8个有界pipe对象、每个4KiB、每任务16个token引用，以及子任务
0/1/2路由。空pipe仍有writer返回would_block，最后writer关闭后EOF，
无reader写入为broken pipe。当前libc保留暂不可用的EAGAIN，由调用者重试；
尚未提供完整阻塞pipe fd语义，不能把短消息管道测试推广到任意流水线。
dup2和fcntl支持当前有限fd模型；posix_spawn文件动作只把0/1/2送入孩子，
其他fd不继承。文件stdio按路径重新打开，不提供跨进程共享open-file-offset；
不应将本接口称为完整POSIX继承。waitpid只支持指定正PID的阻塞等待；
WNOHANG暂明确ENOTSUP。

路径最多255字节、ASCII FAT32/LFN；没有符号链接、POSIX权限位、所有者或
可执行位。执行取决于XOS装载校验。access检查存在/基本读写能力，X_OK在0019起对普通文件按受支持ELF元数据真实校验（普通数据EACCES，
缺失ENOENT），目录允许遍历；sysconf仅实现明确资源值。没有墙钟，gettimeofday返回ENOSYS；
mmap/munmap/fork/vfork同样明确失败。工具移植须按实际调用点选择上游已有
回退或记录最小补丁，不能以永远成功的stub通过链接。

## 已执行 gate

`python3 tests/runtime_smoke.py` 在临时512MiB盘运行标准C main程序：按路径读源、
写产物、8MiB堆、目录/临时文件、子工具17/23退出码、环境与cwd、管道/EOF、
stdout重定向、缺失文件/工具与无授权失败，离线比对源和产物，三轮资源归零。
这只证明受限工具基底；真正binutils的验收另见后续E08-3记录。

## 0019：C++ 启动与静态 TLS 运行基底

POSIX main前运行preinit/init及legacy ctors；正常exit经newlib atexit按顺序运行
全局析构、legacy dtors/fini，静态.eh_frame有可用GNU注册函数时注册与注销。
真实libgcc回溯已运行；libstdc++/libsupc++和C++ throw/catch/RTTI gate仍未交付。
用户态ELF/ISA后端装载静态local-exec TLS，内核只保存/切换线程指针，见e04与0019。
这不提供线程、动态TLS/模块；也不对kill/fault强行调用析构。8组新功能通过，
不能据此声称GCC/G++或E08-5已完成。

## 0021：正常退出时的非平凡 TLS 析构

SDK v5提供真实GCC调用的__cxa_thread_atexit入口，单进程/单用户线程私有malloc链表，
LIFO、先移除节点再调用，允许析构中新注册；失败返回非零。强exit覆盖main返回和
显式exit：先TLS，再newlib退出handler/全局析构，再stdio与_exit；递归exit直接_exit，
不承诺继续运行剩余析构。_exit/kill/fault仍不保证正常清理，无DSO卸载或多线程。
两条正常出口、TLS LIFO/新注册/global/fini顺序与资源回收已在真实客体通过，
f40c9a254b5433d7，报告build/tls_exit_smoke_report.json；完整哈希见0021工作记录。
这不替代目标标准库/异常/RTTI或原生G++ gate。v5路径与从端任务见state/协调页。

0022已通过目标标准库/异常展开/RTTI/局部静态/TLS设施的早期ABI与原生G++ gate，
固定静态配置内可用，详见e08_cpp_seed.md及reports/e08_acceptance.md；上文“尚未
交付”为历史阶段状态，不扩大为完整标准库或多线程支持。
