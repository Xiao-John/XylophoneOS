# 审计后续实施与十项规划交付

2026-11-12。用户明确授权：继续实现、修复并提交 PR；无法在本机运行 XOS 的项目可不做
客体验收，但不得将未运行写成通过。本轮以初审提交
`158a9b99550c03b97e74e3b9e4c2fd6a288c8bf3` 为起点，并同步工作期间新增的上游
`ddcbefa95bfbe0b56f02118dfa2055fe8043b6be`（PR #112，IPC bulk grant），随后再次同步
`7bb3209cbae87b04ddbcbbd5399d7ddc1645dde5`（PR #118，浏览器计划证据门文档）。

本报告接续而不改写 [初审报告](../comprehensive_audit_20261112/README.md)。旧报告的
57 项修复、256 项检查及历史 guest 结果属于其各自源码版本，不能计为本轮组合验收。
本轮代码、回执和调查交付到同一 PR #116；没有合并主线、创建 release 或替换已发布资产。

## 一、结论

十项规划对应的可实现代码已推进到可评审状态，包括正常 COW fork、事务式内核写出、
文件/目录 identity、实际进程 CPU 时间、设备授权与用户态网卡、运行库源补丁、图形
测试迁移、原生开发矩阵，以及构建时来源记录和候选构建入口。

这不等于十项规划全部达成原来的验收条件。三个历史故障仍未定位：Pillow worker 的
`_malloc_r` 缺页、D13 legacy Qt 退出超时、D14 SSG/Notes 退出超时。完整目标构建、
guest、Qt/CMake 集成和硬件路径未完成验证。更广的 TCP/IP/TLS、旧内核驱动迁移、
PCM 音频、SMP、自举、xypm P3 等仍是独立开发工作，未通过改状态文字宣告完成。

本目录 `validation.json` 与逐项日志记录根工作树组合检查；各工作记录中的宿主检查
另有自己的源码边界。`candidate_attempt.json` 保留实际候选构建在 NASM 缺失处失败的
事实，没有用旧镜像或下载二进制冒充本修订的运行结果。

## 二、十项规划逐项交付

| 原规划 | 本轮交付 | 尚未完成的部分 |
|---|---|---|
| 1. 固定可复现构建环境 | `bootstrap_toolchain.py` 导出/恢复带清单和哈希的固定 Linux 工具前缀；实际 tar、权限、链接恢复回归；`build_candidate.py` 串行构建并保留失败回执 | 当前没有锁定交叉编译器、NASM、QEMU 与受信完整工具归档，未实际恢复完整环境；不改版本锁来制造可用 |
| 2. 客体验收与补丁发行 | 候选目录隔离、明确 dash 回执、manifest 绑定、失败即停、可选 smoke；发行脚本拒绝覆盖冻结目录；PR 交付本次实现 | guest/release smoke 未运行；没有发布补丁版本或更新已发布 SDK |
| 3. POSIX 文件 identity | 单对象单 FIL、多打开描述、延迟删除、打开实例 rename、空目录替换、cwd 身份与继承、近满 FAT fixture | 客体满盘、断电恢复和真实 shell 组合未运行；没有增加 hardlink、symlink 或持久 inode |
| 4. VM3 与 COW2/COW3 | 每线程有界 copyout 事务、跨页准备/提交、OOM 回滚、阻塞 pin 提交、普通 COW fork、eager 对照、父退出后已提交子进程存活、CPU 记账 | 中断/页表硬件和完整客体矩阵未运行；活动设备/bulk 映射须先 unmap 再 fork |
| 5. IPC 新组合与 bulk | 完全采用最新上游 actions 19–23 的 grant ABI；开放可调用位 `0x1f`，SDK 单独记录本组合 guest 未运行；保留 IP5 兼容/回退/计数探针；修复 bulk 与 fork、批量 close 的组合边界 | 本轮 bulk/快路径/延迟分布未跑 guest；上游历史资格不转绑当前组合 |
| 6. 设备授权与用户态驱动 | sys112 grant/MMIO/连续 DMA/IRQ/revoke/exit；supervisor 授权 building child；用户态现代 VirtIO-net、原始帧服务与显式网络 QEMU profile | 实际 PCI/PIC/DMA/IRQ/ARP/reset 未跑；无 IOMMU、TCP/IP、DNS、TLS；显示/PS2/ATA 旧驱动未全部迁移 |
| 7. 运行库、依赖头与 Python | newlib `_Atomic`/tgmath 源补丁；真实 CPU 时间接入 times/clock/pthread；CPython sleep 进入内核等待并释放 GIL；错误传播与线程探针 | 新依赖完整目标重建未做；预编译 libm 缺 csqrtl；Pillow 历史分配 fault 未定位 |
| 8. 桌面与 SSG 生命周期 | 31 个旧图形 runner 按 Display+Interactium 迁移；真实双窗口 fixture、像素/游标与服务死亡预期；QPA 局部 expose/焦点修复；SSG 绝对期限修复 | Qt 与图形 guest 未运行；D13/D14 根因仍未定位，完整 stress 与 M2 客体边界未跑 |
| 9. 原生开发 SL3/SL4 | 明确系统/SDK/Make/dash/Seed 回执选择；真实多翻译单元 C/C++ 工程和 shell 继承矩阵；修复 inherited cwd 启动编码与 loader errno 域 | 当前产物不足以执行完整 guest GCC/G++、Make 与嵌套 dash；探针代码不等于已验证原生开发环境 |
| 10. 构建时依赖来源记录 | compiler/source/object/member 字节关联；newlib/GCC/Qt/双 SDK hook；跨 SDK 导入保留原始 build id；license/release 校验覆盖与 legacy 边界 | Qt CMake 和完整依赖目标构建未跑；历史 derived 来源报告及预编译 archive 不升级为同次捕获 |

## 三、关键实现及影响

### VM、写出和生命周期

`user_copyout` 在每线程记录最多 64 个 COW 页，先准备所有写出范围，确认映射仍一致后
一次提交。失败回滚已分配的替换页，不先消费输入再因后续页 OOM 丢失数据。普通可写
共享映射保留共享语义；等待 pin 与调度前完成必要提交，避免阻塞后使用失效的目标。

普通 fork 使用 COW，`--eager-fork` 保留对照。父进程正常退出或故障后，已经提交的
子进程脱离父等待关系继续运行；构建中的子进程仍回滚。显式取消的后代终止关系单独
保留。文件描述与 cwd 继承在子进程可运行之前完成。

新 sys89 版本 1 返回进程 user/system、当前线程和已等待子进程 CPU 时间，单位为
纳秒。内核在现有 PIT 标定阶段校准 TSC，在调度/中断/syscall 边界记账；没有修改
系统单调 deadline 时间域。当前假设单 CPU、稳定 TSC，标定失败时接口报告不可用。
`times`、`clock` 与 pthread CPU clock 不再把墙钟当作 CPU 时间。

具体边界和回归见 [6bd8c261](../../work_log/6bd8c261_vm_cow_runtime_cpu_accounting.md)。

### 文件/目录 identity 与加载器

文件服务以对象身份持有唯一 FatFs FIL，独立 open 各有逻辑偏移，dup/fork 共享 open
description。允许多个普通读写打开，不关闭 FatFs 锁来绕过冲突。加载器另用显式只读
pin，阻止正在装载的可执行字节被并发写入。

打开实例可 rename/unlink；路径消失或被新文件替换后，已有句柄继续引用旧对象，最后
引用关闭才释放 backing。目录替换检查空目录与祖先关系，支持短名/长名身份。cwd
由服务保存目录引用，rename 后跟随原目录，删除重建不会自动切到新目录。

集成时额外复现并修复了两类加载错误：继承 cwd 使用空指针表示时，startup 打包必须
写入约定的空字符串；启动失败必须按已有诊断 stage 区分 files 与 kernel 错误域，避免
把进程资源/状态错误错误翻译为 ENOENT 或 EBUSY。实际 libc→loader 回归覆盖这两条路径。

wire v2 的新操作是 cwd_set=26、cwd_get=27、resolve_path=28。identity 为本次服务
生命周期内的 16 位单调值，最多 65,534 个已分配身份；最多 256 个在引用对象、32 个
全局 open description、8 个会话。它不是跨重启持久 inode，也不提供 hardlink/symlink。
FAT 任意断电原子性没有因此获得保证；失败仍通过 recovery gate 处理。

详见 [文件身份契约](../../contracts/file_identity.md)与
[b8e04c2a](../../work_log/b8e04c2a_posix_file_identity.md)。

### IPC、设备和网络

本轮工作期间主线新增 IP4 bulk，集成时弃用独立草案，保留上游 19–23 的 create、
delegate、map、unmap、close 及其既有布局。运行时支持位表示接口已可调用；新 SDK
把 guest qualification 分开记录，避免把本轮的“未运行”写成“接口不存在”或“已验收”。

组合检查发现普通 fork 会把活动 bulk 页转为 COW，改变 grant 共享和撤销假设。因此
活动 bulk/设备映射时 fork 返回 busy，先 unmap 再 fork；仅持 grant handle 不阻断。
另外，批量 close 的每个 unmap 单独预检不能保证整批成功：第一处拆分可能耗尽最后
一个 reservation 槽。现按真实删除顺序在独立 scratch 中预演全部变更，再整体撤销。
scratch 不占线程 4 KiB 内核栈，仍由现有单 CPU syscall gate 串行化。

设备授权只由 supervisor 向其真实 owned、building child 发出，不以进程名当作权限。
MMIO、连续 DMA、IRQ 等对象有配额、token、pin 与退出回收。当前 DMA 回收 profile
只支持可独立观察 reset 完成的现代 VirtIO-net；没有看到 reset 完成时，页和设备进入
quarantine。清 CPU 映射或 PCI pending 位不能证明设备已经停止 DMA。

没有 IOMMU，获授 MMIO 的驱动与设备必须受信。DMA token/配额和 quarantine 不能阻止
恶意驱动向设备写入任意总线地址；本轮没有把它们描述成硬件隔离。

用户态 VirtIO-net 处理现代 PCI capability、VERSION_1/MAC 协商、两个 64 槽 split ring、
收发、IRQ ACK 和 reset。`net-start 41`/`net-stop`/`net-probe 41` 使用既有 supervisor
与认证 IPC；服务提供原始 Ethernet frame。当前不含 TCP/IP socket、DNS、TLS、HTTP
或浏览器联网资格。详见 [网络契约](../../contracts/net_user_driver.md)及
[07374f76](../../work_log/07374f76_ipc_device_network_runtime.md)。

### 运行库、GUI 和构建

newlib 两项错误从补丁源修复并进入构建指纹：原生 `_Atomic` 使用正确初始化，tgmath
保留 float/double/long double 与复数类型及单次求值。没有手改 vendor 的生成头。
CPython 时间桥调用 sys46/sys47，sleep 释放 GIL 并传播实际错误。桥接函数宿主运行
通过，但新的 CPython patch series 尚未在完整锁定源码及目标配置完成构建。

31 个图形 runner 现在按当前 QPA 协议同时管理 Display 与 Interactium。迁移包含
双窗口独立销毁、输入日志、服务死亡、合成游标与 client 图像的区别、Display 独占
探针以及正常退出回收；没有直接删除旧断言来制造通过。QPA expose 改用窗口本地坐标，
隐藏非焦点窗口时不清除其他窗口的焦点。最后复核还修正了 VBE 日志并不存在的
format 字段断言，以及首 compositor present 可能发生于窗口创建阶段的故障预期。
Aurora 输入链路缺少源时间戳，因此报告明确记为 not_measured，并保留实际按键计数，
没有把空延迟列表当作测量完成。

SSG 的真实写出/ACK 循环在重新获得执行机会后检查绝对期限，读取完成时也检查是否
已经过期。旧实现可把迟到 ACK 作为完成或在期限后首次发送；同一组 20 项真实函数
回归中旧版失败 10 项，新版全部通过。这是独立确定缺陷，不是 D13/D14 根因的证明。

来源捕获在真实编译发生时记录 source 与 object 字节，在 archive 实际成员中匹配
对象，再生成 member_manifest。SDK 导入保留依赖原始 build id 与原清单来源，未知
或歧义成员拒绝资格化。普通 SDK 的预编译 libc/libm 明示为 legacy。另修复成功的
`cc -c ... -o /dev/null` configure 探针被误拒绝，以及 tar 安全过滤改变权限后无法
恢复自身导出归档的问题。

详见 [14a518fa](../../work_log/14a518fa_audit_followthrough_runtime_build_gui.md)
和 [SSG 实测报告](../ssg_deadline_lifecycle_20261112/result.json)。

原生工作流的精确 14 组命令、8 进程预算与显式回执参数见
[native_development.md](../../implementation/native_development.md)及
[c274a9e1](../../work_log/c274a9e1_native_development_gates.md)。旧 SL2 和诊断 SL3 入口
现在必须显式传 `--dash-receipt`。本轮原生客体执行为 0/14，不能用 18 项宿主回执
检查或 2 个宿主项目的运行结果代替。

## 四、没有修好的问题与具体原因

### 1. Pillow `_malloc_r` fault

历史 worker vector14 的 RIP 为 `0x4037927b`，CR2 为 `0x60cc5fc8`；旧记录定位到
newlib top-chunk header 写入。缺失原线程 archive、故障 ELF/工作盘，以及 RSP、页错误
码、页表、heap_break、malloc top/锁状态。仅凭 CR2 位于 heap 区间不能判断是坏 chunk
指针还是映射缺失。已经读过 TLS/control、reent 清理、malloc 锁桥、sbrk 和映射回滚，
未得到可复现的源码错误路径。

影响：不能声明 threaded Pillow 或完整 LocalPilot 可用。下一步必须在匹配的线程
profile 记录 fault 线程、FS/control、堆边界、PTE、top chunk 与锁 owner，并与 xsh、
dash fork/exec、native zlib 对照。宿主 glibc/Pillow 运行不能替代该目标现场。

### 2. D13 legacy Qt 退出超时

原 Studio 套件末尾已经打印 `QT_WIDGETS_OK`，input worker 也退出并 join；实际停在
后段 legacy Qt probe 的事件循环返回之后。能够缩小到 QWidget/QApplication 析构、
TLS/newlib 退出和进程等待之间，不能进一步确定是哪一把锁或哪个线程。相同二进制
重跑通过没有提供因果信息。

影响：偶发退出挂起仍可能发生。需要失败时的线程 RIP/RSP、wait kind/target、
closing/exit_owner、锁持有者与析构阶段记录；延长超时不会解决或定位它。

### 3. D14 SSG/Notes 退出超时

原失败串口已经包含两路 Provider EOF 和 Notes input-thread join，Browser 也已回收，
Notes 仍需在 20 秒后取消。当前 pipe release 本就唤醒双向等待者。历史 QThread 改
native pthread 的候选与原版各 8/8 未复现，不能采用该候选并宣布修好。

影响：consumer/Notes shutdown 的历史挂起仍未关闭。需要匹配当前 SDK 的真实运行
记录 provider run/stop wait、native TSS/reent 清理、Qt 析构结束及阻塞栈。本轮 SSG
期限修复不覆盖这个未定位原因。以上三项的原始证据、检查路径和缺失字段详见
[9e72a804](../../work_log/9e72a804_ssg_deadlines_lifecycle_review.md)。

### 4. 固定构建、guest 与发布资产

当前环境有宿主 C/C++、ar/nm、Python，但没有仓库锁定的完整 x86_64-elf 工具链、
NASM 和 QEMU，亦无真实 Qt/CMake 构建环境。宿主严格对象编译使用声明式镜像头替身，
没有链接或引导内核；host mmap/硬件回调也不执行真实 CR3、TLB、PCI、PIC 或 DMA。
候选构建已实际失败并保留日志。PR 可以评审这些代码，不能据此声明新镜像可启动。

旧已发布 SDK、编译器与镜像没有自动获得本次修复。需要后续在匹配环境重建候选并
绑定 manifest 后，另行执行发布；本次没有上传发行资产。

### 5. 范围外的未实现功能

现有 PC Speaker AU1/AU2 代码保留，本轮没有实际音频捕获。PCM AU3–AU5、完整网络
协议栈、显示/PS2/ATA 全部迁用户态、SMP、自举、完整 POSIX 与 xypm P3 不属于本次
已实现结果。不能用新的网卡纵切、工具链搬运或文件 identity 给这些项目勾选完成。
它们仍按仓库原有契约继续开发，具体债项见 [技术债总账](../../tech_debt.md)。

### 6. newlib 长双精度复数库覆盖

头文件修复后，真实 `long double _Complex probe(long double _Complex x) { return
sqrt(x); }` 对象正确引用 `csqrtl`。对仓库预编译 libc.a 和 libm.a 的定义符号检查确认
两者均未提供该符号。这是现有数值库的额外覆盖缺口：类型分派正确并不保证所有目标
函数均有实现。证据见 [真实编译与符号检查](newlib_complex_symbol_gap.json)。

本轮测试确认 float/double/long double 分派、复数静态类型和实数执行；没有声称完整
long double complex 数值库已可链接。需要为锁定 newlib 版本补齐相应实现并重建 SDK，
再覆盖有限值、极值、NaN/Inf、符号零及误差。本轮没有提供这部分数值库实现，也没有
将调用静默降精度为 float/double。

## 五、复核入口

- [组合检查与未运行项](validation.json)：每个命令、退出码和对应日志。
- [源文件快照](source_snapshot.json)：当前代码与测试字节；不包含报告叶子互相哈希。
- [实际候选失败回执](candidate_attempt.json)及 [日志](candidate_system.log)。
- [bug-hunt 题目索引](../comprehensive_audit_20261112/bug_hunt_questions.md)：24 项有源码依据的题目目录；原 `CONTEST/` / `归档_副本.zip` 仍未取得，不能冒充逐字原题。
- [初审逐项处置](../comprehensive_audit_20261112/todo_disposition.md)：初审历史快照；本轮状态以本报告和新工作记录为准。

报告与新增日志由本目录平铺 `manifest.json` 登记。冻结旧报告与 `docs/state.md` 没有改写。
