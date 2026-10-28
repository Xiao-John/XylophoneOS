# E13-T：公共线程与等待契约

2026-10-28，契约v1语义保持。T0–T2与T3-PY已有各自受限资格，QtCore线程接入已有受限实测；
完整T3-QT未单列，Qt资格见[QtCore](../implementation/qt_core.md)；
实现与证据见[线程实现](../implementation/threads.md)和[主题摘要](../history/threading.md)。
当前编号见[ABI登记](abi_registry.md)，不得根据早期“待实施”文字重新领取已交付工作。
本页规定首版线程语义，后续信号/VMA/多线程fork须独立修订和验收，不反向扩大旧资格。

## 模型与范围

采用 **1:1 内核线程、单核抢占**。用户线程可被时钟抢占，不依赖主动 yield 才能
运行其他线程；沿用先前内核不可抢占模型，阻塞 syscall 保存上下文并退出到
调度器，不能在内核里轮询等另一个线程。SMP 后续另验，通用锁与内存序仍正确设计。

首版包含创建/等待回收/分离、互斥锁、条件变量、once、TSS、静态 TLS、正常析构
及有界等待。异步线程取消、实时调度、优先级继承、robust mutex、进程间 pthread
同步、动态 TLS/动态加载、完整信号和 fork 不在首版。请求未支持属性必须明确
拒绝，不静默降级成功；不宣称完整 POSIX threads 合规。

## 不可抢占路径的工作量与等待

对应宪法C20/C24/C25，以下是调度/等待专项约束，不将具体时延或算法写入宪法：

- 运行期不可抢占路径须有明确的最大工作量、长度/批次或受控分段边界；新增大块复制、
  设备提交和共享资源操作在专项设计记录上界与依据，必要时定向测量，不能假定“有限”就无影响。
- 等待用户服务、其他线程或外部事件时必须按等待契约登记阻塞并交还调度，禁止在不可抢占
  内核路径无限轮询等待其进展。短临界区、可证明有界的硬件轮询须说明退出/失败条件。
- 锁序与阻塞条件显式定义；不能持有使完成者无法运行/取锁的资源再等待它。超时、唤醒、
  关闭与进程/服务死亡按同一等待生命周期仲裁，不以忙轮询掩盖丢唤醒或未完成状态。
- 启动初始化、紧急panic等不属于正常应用调度路径，适用范围与结束/停机行为须明确登记；
  不借例外扩大运行期阻塞边界。本次仅确立设计要求，未重新审计或验证所有现有路径的时延。

## 进程、线程、资源与身份

| 归属 | 内容 |
|---|---|
| process_record | PID、地址空间及映射所有权、页预算/堆、父子与进程完成记录、构造权与委派深度、文件会话、端点与句柄/管道引用、退出仲裁状态 |
| thread_record | TID、所属进程引用、调度/等待状态、寄存器/用户栈/内核栈、线程指针、FPU/SIMD、线程退出值与 join/detach 状态 |
| 用户态进程运行库 | FD/open对象表、cwd/env、分配器与进程初始化/atexit；用真实锁保护 |
| 用户态线程运行库 | errno/newlib reent、TSS值、TLS模板实例与析构列表、线程入口包装状态 |

- PID 与 TID 为不透明非零标识；存活期和旧句柄期不复用，溢出返回资源失败。
  getpid 返回所属 PID；gettid 返回 TID；pthread_t 在 SDK 中不透明，不当数组下标。
- 现有 process_wait、kill、构造/委派及监督 Escape 继续操作进程。进程完成记录
  在全组停止后只产生一次；join 不消耗进程完成记录。已有 ps/stats 的进程计数
  含义不改；另提供版本化线程数/等待数/预留数指标，不偷换 tasks 字段含义。
- 线程共享进程的权限与页预算，不复制或增加权限；普通进程可在配额内创建自身
  线程，不需 spawn 构造权。进程创建权/文件会话/委派的所有者从单个 task 迁到
  process，工作线程退出不取消进程的子进程；整个进程退出沿用子进程清理规则。
- IPC 内核身份采用所属 PID，不能把 TID 冒充新增文件客户端或权限。文件端点
  首版仍按进程建会话，同一会话请求在用户库串行化，不改变服务协议为逐线程。
- 地址空间只在进程所有执行上下文停止、内核引用解除后销毁；退出线程的内核栈
  只能在其他安全上下文回收。禁止线程各自执行现有 destroy_address_space 路径。

## 创建、栈、TLS 与生命周期

### 创建事务

定义逻辑操作 thread_prepare → thread_start，及失败 thread_abort。prepare 只操作
调用进程，预留线程槽、独立内核栈、用户栈/guard 和 TLS 区，返回本进程构造句柄、
TID及映射范围；新线程不运行。SDK 初始化 TLS/reent/入口记录，再 start 提交。
失败必须回滚所有预留页/槽；任何本进程线程可在生命周期锁下完成或撤销事务。
进程退出清理尚未提交的线程；prepare 不能增加新子进程或外部进程执行上下文。

T0的最小逻辑ABI面如下；名称是契约名，不表示当前已有同名函数：

| 操作 | 必须保证 |
|---|---|
| thread_prepare/start/abort | 准备/提交/回滚事务；句柄限所属进程，不接受外部PID |
| thread_self/info | 返回TID与自身栈界等已声明字段；不泄漏内核地址或别进程信息 |
| thread_begin_exit | SDK已完成线程清理后原子登记离开，判断是否最后一个，并在最后时关闭新建入口/授予唯一进程收尾责任 |
| thread_exit | 不返回；提交线程退出值，在安全上下文回收；对已领取最后收尾责任的线程完成进程退出 |
| thread_join/detach | 内核持有终态与唯一回收权，等待可阻塞；不依赖用户轮询可能已释放的TLS/栈 |
| clock_monotonic/resolution、sleep_until、wait_word/wake_word | 使用下文定义的时间、身份与阻塞语义 |

begin_exit之后的非最后线程只能执行不依赖共享用户库的最终thread_exit路径，
不再获取用户锁、调用malloc或启动新线程；其余清理在begin_exit之前完成。
“最后”按尚可执行用户工作的线程判定，不把未start预留或死亡join结果当作保活
线程；最后退出时统一撤销未提交的创建事务，不能留下永远无人start的进程。
最后线程收尾仍须等待所有其他上下文安全停止，不能仅因“登记离开”就释放它们
正在执行的页面。_exit/kill/fault绕过用户握手，由内核统一停止和回收。
请求使用固定宽度字段，version/size/reserved严格校验；输入先复制为内核快照。
创建输出区预检/复制失败须回滚预留，不能留下应用无法知道的活线程。
内核逻辑错误到SDK errno的映射至少区分invalid_address/EFAULT、invalid/EINVAL、
denied/EPERM、resources/EAGAIN、out_of_memory/ENOMEM、busy/EBUSY和超时；pthread
层按其约定返回正错误号。具体内核数值在T0头文件中唯一登记。

start 通过版本化请求指定入口、参数、初始栈和线程指针；入口为本进程可执行
映射，栈范围/对齐、TLS 与所属预留区均校验。内核不解析 ELF 或读取 TLS 模板，
SDK 从本静态映像记录复制 .tdata 并清零 .tbss，主线程与后续线程使用同一布局。
不能重新执行全局构造函数、清零整个 BSS、重置全局堆或重复注册进程 fini。

线程栈向下增长、16字节ABI对齐、独立无映射 guard；默认新线程 256 KiB，允许
64 KiB–2 MiB 的页对齐尺寸，另计 guard/TLS/内核栈；不支持调用者自供栈首版属性。
主线程目前128 KiB单列报告，不冒认已扩栈。必须提供当前线程实际 stack_bounds，
供 CPython/C++ 查询；有 guard 不等于任意栈溢出都可恢复。

新增栈/TLS使用独立受保留映射区，不能与 ELF LOAD、堆、主栈/启动区或现有 TLS
相交。T0 先冻结具体地址图及兼容策略；当前静态 TLS 小窗口不能直接塞进所有线程。
新布局若排除旧 ELF 可用地址，必须通过 SDK/映像 ABI profile 显式区分或明确
拒绝，不静默破坏旧 ELF。不得把所有 ELF64/x86-64 都当作支持新运行库布局。

首版工程上限：8个进程保持不变，每进程最多4个线程（含主线程与预留/未回收
joinable线程），全局最多32个线程槽。进程仍共享原256 MiB用户页限额；内核栈页
另计入真实物理消耗。额度不足返回EAGAIN/ENOMEM，不从其他进程偷槽。静态槽的
内核映像体积与启动载荷预算必须在T0核验；更改上限需带证据更新本契约。

### 退出与回收

| 触发 | 首版语义 |
|---|---|
| 线程入口 return / pthread_exit(value) | 只结束调用线程，执行本线程正常清理；join观察同一个value |
| main return / exit(status) | 进程正常退出；阻止创建，停止并等待其他线程脱离执行，调用者TLS清理后执行进程atexit/fini/stdio收尾，最终发布一次状态 |
| _exit、监督kill/Escape、任意线程致命异常 | 结束整个进程并回收，不执行用户析构；故障保留实际TID/PID、向量和地址 |
| 最后一个线程正常pthread_exit | 进程退出0；SDK与内核退出仲裁保证其他线程清理已结束，再执行一次进程正常收尾 |

进程关闭阶段禁止 prepare/start；退出并发由唯一仲裁者发布终态。最后线程的
“确认最后 + 禁止新线程 + 领取进程收尾责任”必须原子完成，不能在用户态无锁
数线程。实现需提供对应退出握手；内核绝不直接调用用户析构。exit调用者正常
清理不保证成功：其他已停止线程可能持有用户锁；首版不承诺exit修复死锁或运行
其他线程的析构，_exit/监督取消是明确的强制终止路径。用户自行join后exit才有
完整应用级清理保证；不能为掩盖死锁把析构伪装成已执行。

joinable默认；同进程一个join者取得回收权，返回时目标TLS/reent清理已结束、
执行已停止，结果只消费一次，栈/TLS可以安全回收。自join报EDEADLK；无效ID报
ESRCH，已detach/已有join者报EINVAL。不承诺自动发现任意锁/多线程等待环。0037澄清：detach/成功join完成回收后，
旧TID已失效，后续操作报ESRCH；仍有记录的detached目标/已有join者报EINVAL。
detach支持运行中或已结束但未被join领取的线程；终止后安全自动回收。线程ID
不得因槽重用指向后来线程。执行资源死亡后尽快回收，保留小型join结果和配额槽
直到join/detach；不能累积整份死线程栈。主线程pthread_exit也遵循同样语义。

TSS key是进程对象、值是线程对象；key删除不调用析构。正常线程退出先执行
C++ thread_local析构，再进行pthread TSS析构（最多4轮，调用前清空该值，允许
析构重设）；newlib线程重入状态最后释放。静态TLS存储在所有依赖清理完成前有效。
不为这一定义推导完整跨语言析构顺序标准合规；C++与pthread混用需独立测试。

## 等待、唤醒与时间契约

内核提供进程私有 wait_word/wake_word；用户库在其上实现pthread锁/条件变量。
等待键为“所属进程身份 + 对齐的32位用户地址”，不是裸物理地址，不允许跨进程
唤醒。逻辑请求为 wait_word(address, expected_u32, deadline_ns)，内核在同一个
临界区中校验/比较、入队和设置blocked，wake与该临界区串行，不能穿过睡眠登记。

| 情形 | 返回/效果 |
|---|---|
| 地址非4字节对齐、非有效可写用户映射 | invalid_address；不入队 |
| 当前值不等expected | value_changed；不入队，不算超时 |
| 值相等且截止时间已到 | timed_out；不入队 |
| 值相等且尚可等 | 入队并阻塞；唤醒或超时后返回，允许伪唤醒 |
| wake_word(address, max_count) | 按入队顺序唤醒至多max_count个，返回实际个数；0无操作，UINT32_MAX广播；不存储“未来唤醒” |

映射校验与入队在地址空间生命周期保护下完成；等待期间禁止移除/重用对应映射，
相关释放返回busy，或先通过受控协议结束等待。首版选择**busy拒绝解除映射**，
进程终止统一移除等待者后销毁空间；不能sleep后访问已释放页。用户同步对象本身
必须活到没有等待者，free后复用同地址不由内核修复，这是调用方责任。

超时使用绝对 CLOCK_MONOTONIC 纳秒截止时间，UINT64_MAX代表无限，0为立即检查；
计算溢出必须拒绝/饱和到合法最大值，不绕回早期时间。当前100 Hz tick可先提供
10 ms分辨率，实际分辨率由clock_getres报告；到期向上取tick，不能提前超时。
时钟持续非递减，不在调度切换后归零。时钟、超时出队、wake、线程/进程退出对同一
wait记录只完成一次，伪唤醒后由调用方重新检查谓词，不从头重置绝对截止时间。
低层提供clock_monotonic、clock_resolution和sleep_until；墙钟已由PY3 B2受限实现；VM暂停校时和TLS证书时间用途另验。tick只证明单调时间，不证明时间戳、墙钟或睡眠延迟上界。

用户mutex解锁用release、加锁成功用acquire；wake本身不代替共享数据的内存序。
条件变量用受锁保护的谓词及序列号/等价协议，保证观察序列、释放mutex、入睡与
signal之间没有丢失唤醒；返回前重新获取mutex，超时也一样。用户同步慢路径可以
短暂重试，但等待必须进入blocked，不能用长期yield轮询冒充阻塞。锁快速路径在
用户态，内核不认识pthread、Python、Qt对象。首版只承诺普通调度公平性，不保证
mutex严格FIFO或实时期限。

## pthread、libc 和 C++ 的首版面

提供pthread_create/self/equal/join/detach/exit；attr的joinable/detached与栈尺寸；
mutex的normal/errorcheck/recursive及trylock；cond的wait/signal/broadcast及
CLOCK_MONOTONIC显式clock属性；once；key_create/delete/getspecific/setspecific。
线程函数遵循各自标准返回约定，例如大多数pthread函数直接返回错误号，不把
负kernel错误码或errno接口混给应用。pthread_getattr_np/stack查询只提供已实现
字段供实际消费者使用。POSIX sem_t不默认包括，需要CPython时另做真正有计数的
sem实现或选择已验证的mutex/cond后端。

默认cond时钟若采用标准CLOCK_REALTIME而该时钟仍不可用，cond_timedwait必须
明确ENOTSUP；不可偷换成uptime。CPython与Qt首批选显式monotonic路径；若固定
上游不能选择该路径，应补真实墙钟或小范围适配，不伪造成功。普通cond_wait不
依赖墙钟。unsupported属性/进程共享锁/scheduling返回ENOTSUP，已知错误配置
返回EINVAL。静态mutex/cond/once初始化器必须并发安全，销毁有等待者返回EBUSY。

threading-safe SDK是独立新profile；内核有线程不代表旧SDK可安全创建线程。
旧SDK不导出线程创建入口；新SDK和用户包装在第一次pthread_create前完成进程
运行库初始化。不得把不安全旧库通过新pthread头重新打包成“已支持”。

T2必须同步完成：

1. newlib每线程_reent/errno真实隔离；按实际构建选择TLS或__getreent，不在被
   抢占用户态修改共享_impure_ptr冒充TLS。核验目标库single-thread配置，必要时
   重建；malloc/free/realloc/sbrk、stdio、环境和其他实际使用的newlib锁钩子有效。
2. FD表/对象引用、cwd/env/目录状态有锁和生命周期规则；cwd/env进程共享，
   应用仍需同步依赖它们的复合操作。同一open对象的seek/read偏移更新串行，
   不把逐syscall线程安全说成“seek+read组合原子”。
3. 文件Client的request_id/request/response及整次请求响应序列受会话锁保护，
   不允许线程互相取走回复；单线程阻塞文件操作不能锁住全进程其他无关资源。
   公布锁序，禁止持有FD表全局锁再调用可能分配内存或阻塞的服务。
4. 静态TLS与逐线程析构列表，pthread once/TSS，C++局部静态guard、atexit注册、
   异常运行时的逐线程状态均审计；引入线程不只是改__cxa_thread_atexit的链表。
5. libgcc/libstdc++的gthread配置与真实pthread后端匹配；重建并绑定头和归档。
   std::thread、mutex、condition_variable、call_once、thread_local分别测试，
   不因C pthread通过自动宣布C++或Qt通过。旧single模型产物保留原回执。

进程stdio/文件句柄共享，不等于已有跨进程FD继承/阻塞pipe完成；dash B2/C继续
按自身gate交付，可复用等待机制，不能把线程gate代替Shell管道或fork验收。

## T0–T3 计划与退出条件

| 批次 | 实施范围/出口 | 定向客体gate |
|---|---|---|
| T0 | 拆process/thread记录；确定ABI版本/请求布局/保留地址图/预算；prepare/start/abort、退出握手及原有进程生命周期兼容 | 两线程共享计数但栈/TLS/FPU隔离；不yield仍被抢占；非法入口/栈/TLS/越权拒绝；创建各阶段失败回滚；thread_exit不杀同伴；process退出统一回收；原spawn/委派受影响用例 |
| T1 | 单调时钟、sleep_until、wait_word/wake_word、超时队列与终止清理 | 强制编排“比较/入队/唤醒”竞态；先wake后wait；值已变/地址错/跨进程同地址；超时与wake同时发生；等待中kill/映射释放busy；空闲等待状态可观察；资源回基线 |
| T2 | pthread与线程安全newlib/SDK/C++运行库profile，发布冻结SDK回执 | join/detach互斥、自join、耗尽回收、last-thread仲裁、退出竞态；mutex/cond生产消费与超时；once一次；TSS四轮/errno/TLS析构；并发malloc/stdio/文件请求；C++各项独立客体验证 |
| T3-PY | CPython改真实pthread后端；保留GIL，退出临时thread-stubs profile | threading/Lock/RLock/Condition/Event/Queue、后台线程与主线程阻塞I/O；进程退出/异常与资源回收；按固定版本选择上游测试子集 |
| T3-QT | 固定Qt配置后接QThread/QMutex/QWaitCondition及事件投递/定时器 | 后台线程→主事件循环唤醒、退出join/析构；通过不代表整个G01或QtCore完成 |

T0先交结构/ABI与创建退出的最小客体结果，再扩T1；T1/T2可按已冻结接口分工，
不能在同一文件争改。T0/T1通过不向一般应用宣传线程安全SDK。**对外多线程可用
的门槛是T2；对Python多线程可用的门槛是T3-PY。** CPython可继续单线程bootstrap，
不等T3才能做语言功能；T2交付后线程适配立即前移，不等PY3其余生态功能。

本计划只安排定向功能/竞态与受影响回归，不重复已完成压力。压力专人基于新
SDK/系统回执另安排长时间创建销毁、内存高水位和随机调度；未测仍写not_run。
每批报告固定源码/ABI/SDK/机器配置、命令/输出/状态、产物哈希、资源基线/峰值、
失败与未运行项；记录的线程数包括预留/等待/join结果，不能只看可运行线程数。

## 实施所有权与文件结构

实施所有权按state当次登记；移植线提交缺口探针，公共ABI/运行库由对应负责人整合。
不根据旧分配推定朋友或agent仍活跃；不把本契约当作派工授权。

- `src/kernel/core/`：进程/线程生命周期、配额和等待队列的通用部分；按实际需要
  拆小文件，不能把现有x86 tasks.cpp整份搬过去并保留汇编。
- `src/kernel/arch/x86_64/`：上下文、线程指针、FPU、页表操作适配；PC计时硬件
  留在platform/pc，不在公共pthread或Python里访问PIT/RTC。
- `src/shared/include/xos/`：版本化线程/等待ABI；不暴露内核记录指针。
- `src/user/sdk/`、`src/user/libc/`：创建包装、TLS/线程安全运行库与pthread后端。
- `tests/threading_*`与独立夹具：定向guest runner；`docs/work_log/`保留实施回执。

新任务实施前登记具体文件占用、实际SDK与资格输入；共享build排他串行。实现
改变ABI时同步e04_loader_sdk.md、体系结构说明和SDK manifest；保留旧快照和
0.0.1附件，不静默替换旧产物。第二ISA只做新通用代码编译检查，不叫新ISA移植。
新自研代码Apache-2.0，历史/第三方条款按licensing.md保留。

参考：本契约中的资源/退出限制为XOS首版选择，标准接口部分以固定版本实现复核。
[POSIX条件等待](https://pubs.opengroup.org/onlinepubs/9799919799/functions/pthread_cond_clockwait.html)、
[newlib重入与锁](https://sourceware.org/newlib/libc.html)、
[libstdc++线程配置](https://gcc.gnu.org/onlinedocs/libstdc++/manual/configure.html)。
