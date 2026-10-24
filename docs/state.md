# XOS 当前状态

更新时间：2026-10-24（Asia/Shanghai）。新 agent 按 AGENTS.md 的阅读顺序开始。

## 当前方向与协作状态

以 xos_plan.md v0.5 正文、后续决定和本页状态为准。下划线命名、轻松开发、过程落盘；
固件/ISA/平台/通用内核分层。localpilot/ 独立，不进入 XOS 构建、扫描或清理。
顺序 E05 → E07 → E06 已完成。E08-1、E08-2、E08-3 的受限 gate 均已通过；
E08-1至E08-6当前约定的受限功能gate均已通过；E08功能闭环收口（0022）。
综合证据见reports/e08_acceptance.md，不冒称最终镜像全量旧回归或压力全绿。

本组协作已结束：主agent完成统一构建/验收/文档；kernel/files/loader Luna分别完成
机制、文件运行时、GNU构建/补丁。没有剩余占用的编辑范围；责任和失败过程见
work_log/0013_e08_2_runtime.md与0015_e08_3_binutils.md。新一组重新登记范围，
仍不得并发构建/清理build/，GNU专属cache构建使用独立SDK快照。

Git origin 为 Xiao-John/XylophoneOS。0023按用户明确授权提交、推送并发布发行，
使用本机凭据且不将凭据落盘。原日常 work_disk.img 保留，测试均使用临时专用盘。

## 0023完成：首个正式发布

用户授权今天发布GitHub xiao-john/xylophoneos正式Release，版本0.0.1-1024。
主端占用scripts/package_release.py、发布文档/README、独立build/releases/、Git提交/
标签/Release上传；压力从端仍占用其测试/报告，不覆盖或清理其build路径，不并发
make build。发布先复制已验证镜像/SDK到独立目录，打包验证只操作发布副本。
GNU对应源码、许可、安装工具链映射/校验与启动说明随包提供；不得读取/纳入localpilot。
2026-10-24 23:53:21 CST正式公开Release（draft=false/prerelease=false），8项附件上传并核对远端摘要。
标签v0.0.1-1024绑定0e541badf27a23e2928881279cff5f165de8b4c9；内核build仍为2c3876e640840ff5。
SDK C/C++宿主编译和四项新包客体验证通过，见work_log/0023_first_release.md。
发行回执releases/release_0_0_1_1024.json；压力从端的测试/报告未纳入本组提交，仍由其维护。
发布工作已结束；后续修复使用新版本，不移动此标签或静默替换发行镜像。

## 0022完成：原生G++与E08功能闭环

接收A/B后，六项早期ABI客体通过；E08-5原生G++设施4组/14命令通过，
6b7d5cfc3612fdf4，资源[130342,2,0]。实际修复TLS回退重复定义和g++ lrealpath漏返回，
原始输入不覆盖，派生入口/安装命令见e08_cpp_seed.md与work_log/0022_cpp_seed_acceptance.md。
当前最终系统2c3876e640840ff5，xos.img SHA256
1c2cfa90d65b9a9585ac3d5cef32c8376b1806e65f7502321912b2e15b54454c。
E08-6 C++编辑→重编→运行→sync→重启通过4项/18命令，结合0021已通过的C增量，
主端判定E08受限功能验收通过，O11/O12/O13在固定静态配置通过。单语言原报告
仍标partial，综合报告reports/e08_acceptance.md、build/e08_acceptance_report.json
分别绑定测试版本；没有重跑C/旧CRT/历史压力，也不把旧证据归到最终镜像同一次测试。
最终系统与native gate相比仅更新目标库许可登记，实际CRT/库/头与SDK v5一致。
目标库与修复G++分别在.cache/xos_seed/gcc/relinks/target_runtime_v5_receipt/、
gxx_lrealpath_v5/；组合白名单build/cpp_bundle/。不要使用原始B g++（仍含已暴露bug）。
原生G++产物848056字节；最终编辑重启C++产物791368字节，完整hash见0022。
collect2、动态链接/TLS、线程、完整POSIX/标准库、自举不在范围；真实内存/磁盘
高水位和后续压力仍由专人负责。327项源码hash与manifest一致，7份许可材料检查通过。
本组结束，没有剩余代理占用或QEMU。下一步按计划E09交付/朋友试用，尚未开始；
Qt、系统重建、自举不因本组通过自动开工。下面0021/旧阶段保留作历史。

## 0021历史：E08-5与E08-6准备

用户授权开始E08-5，争取2026-10-24晚进入E08验收。主端负责libc/ABI/SDK、C++
安装整合/正式gate、共享文档与build/串行构建/QEMU。从端任务已写
prompts/e08_5_secondary.md，外部从端待用户转交/启动，不能误认为已经运行；独占
GNU构建脚本/ports/gcc及新e08_5私有cache，优先分批交target运行库，再交g++/cc1plus。
本轮两位Luna均已交付冻结，主端当前持有共享文件和build/，没有其他编辑占用。
主端新运行基底f40c9a254b5433d7已构建，TLS main-return/显式exit两条客体路径通过，
资源[130342,2,0]；SDK v5冻结到.cache/xos_seed/sdk_snapshots/3a302b5cd7e1cdab0f594b0d16d7ca92b753fec7b2efcc6347b01e5a69542edd，manifest SHA256同名。
新增__cxa_thread_atexit/正常exit TLS先于global析构，不改内核ABI；旧快照保留。
C++安装/profile合同5例、v5 target sysroot readonly预检、许可材料核对通过。
E08-5仍not_run；E08-6提前验证的C部分已通过4项/18命令（82ffcecab8ccbcce），
报告build/e08_6_c_report.json；旧测试镜像/manifest已保存，不因新构建丢失绑定。
完整记录work_log/0021_cpp_seed_start.md。等待从端分批交真实target库/G++后继续
独立ABI→原生G++设施→C++编辑/重启增量。C++未验，不标E08-6/整体通过。
不重跑已完成C gate/旧压力，后续压力由专人负责。

## 0018–0019历史：E08-4/5分工

0018已写好主agent（含Luna）与另一协作agent的执行prompt，入口
[e08_4_5_coordination.md](e08_4_5_coordination.md)。主agent负责ABI/运行基底/集成/验收，
协作者负责GCC/G++构建和依赖闭包；build/归主agent串行使用。
用户已启动从端；主agent现在启动实施。主agent独占内核/loader/ABI、构建集成、
共享文档和build/；luna_runtime负责指定libc分析/实现，luna_cases负责新增测试；
从端独占GCC构建/ports/gcc与私有cache；Luna本组任务已交付，暂无其活跃编辑占用。
详细分工见协调页。最新0020已接收并验收C Seed，Luna均交付且无剩余编辑占用；E08-5仍not_run。
主端0019已通过CRT/静态TLS/exec-access/真实libgcc回溯/拒绝路径8组客体功能
（9830f208cc2095a4）及12例TLS解析检查；通用loader两文件AArch64仅编译通过，
SDK v2已冻结到 .cache/xos_seed/sdk_snapshots/f5c74adecb9515878fdbce14a56062cb0567772ae183edecf2a455d15a1f9f74，
供从端构建使用；不包含libstdc++/libsupc++，不能当GCC/C++阶段完成。
从端<algorithm>阻塞已回复：由从端先构建真实host静态标准库闭包，继续指令在
[主端回复](reports/e08_gcc_primary_reply.md)，不等待主端另交预构建STL。

## 0020已完成：C Seed集成与验收

E08-4受限功能gate通过，构建82ffcecab8ccbcce，xos.img SHA256
bd5dd6d7342b42ce5904f0937675c3285f9058fa93d0568792b63e3d31530a8d。
4组/15命令：真实GCC/cc1/as/ld多文件归档链接与执行、libgcc128位辅助函数、
错误路径、源码逐字节保护；每条资源恢复[130342,2,0]。完整证据和接续命令见
[0020](work_log/0020_seed_integration.md)、[C Seed使用](e08_gcc_seed.md)。
修复lrealpath漏返回值、O_NOCTTY拒绝、as安装名和8-open链接容量缺口；
文件消息布局不变，每会话16打开/全局32锁。SDK v4冻结为
.cache/xos_seed/sdk_snapshots/1ba7c52c568725cac63c4a9e603aabd61f30e00db430ca0e5afb4fcfee956490，
manifest SHA256同名。派生Seed为.cache/xos_seed/gcc/relinks/open_capacity_fix/seed_manifest.json；
不要使用从端原始gcc二进制（仍含已暴露bug），原始manifest只作来源证据。
预检18例、diagnostics9例通过，7份许可材料与登记GNU组件哈希核对通过；
C++ ABI runner已准备，拒绝host运行库的guard通过，真正目标库/客体ABI仍not_ready。
当前没有代理剩余编辑占用，不重跑旧CRT/TLS/压力测试；压力仍由专人负责。
collect2未重链接/未验收，当前profile直接使用真正GNU ld，不扩大构造权。

## 本组修复与测试边界

0017 已完成：主 agent 仅修复 S2 暴露的 libc 初始文件偏移错误；普通 open 从0、
O_APPEND 从EOF。文件位置探针及原现场 archive final-link/执行/strip 定向回归通过。
没有剩余编辑占用；不重跑 S0/S1/S3/S4 或 make smoke，后续压力测试由专人负责。

当前定向验证构建 b1ded17e673ccffc，xos.img SHA256
baa37982b222a59a836def90c4586be70743ea88e26ac9b70843c8fa5f97507d。
新 Seed 为 a983a603cb4132f7ff02bc3471978e5099e28dad7a60f8a33658358938f14479，
manifest SHA256 4986571a249ba23a814454848837eaebb0791dbb5dc6273c563df1c141dc4193。
运行时已静态链接进新工具，旧 Seed 仍含 bug，不应与修复版本混用。
对应 SDK 快照 f187691498b56720feb7ee118ad6cd70b2808cd4145ad7d4ea3d640ee51a1a93。
证据 build/archive_link_regression_report.json、file_position_regression_report.json、
work_log/0017_archive_position_fix.md；下面5276ff16全量结果仍属于历史版本，
不冒称本次全量已复验。S2 原压力失败报告保留，定向修复不将整份压力测试改成全绿。

## 当前已实现

- 0001–0006：实模式练习、BIOS/x86-64 内核、异常/页管理、ring3、抢占、IPC、监督回收。
- 0007：E04 用户态 ELF 装载、SDK、argv/stdio、启动/等待/退出/故障结果与回滚。
- 0008：E05 文件/编辑器；0009：E07 ATA PIO、用户态 FatFs、同步和正常重启持久化。
- 0010：E06 newlib 4.6.0.20260123、libc_hello、用户任务 FXSAVE/FXRSTOR。
- 0011：E08-0/pre1 资源审计与设计；0012：E08-1 存储/会话/流式装载 gate。
- 0013：E08-2进程/libc/stdio/动态堆；0014：许可管理；0015：真正GNU binutils Seed。

当前机制：

- QEMU pc-i440fx-10.0、qemu64、TCG、单核、512 MiB RAM，无网络；只读软盘启动，
  独立 IDE 工作盘。物理页管理上限 512 MiB；1 GiB 用户窗口、65536 页/任务
  （256 MiB，含栈）、8 任务、16 未收集完成记录。分配提示与页表回收经过压力验证。
- 新盘默认 2 GiB FAT32 稀疏镜像，显式 make disk 创建；已有 16 MiB FAT16 可继续用，
  不自动格式化/迁移。512 MiB 与 2 GiB FAT32 均已运行验证。工作盘独立于 build/。
- ATA PIO 仍在 kernel/platform/pc：LBA28、每次最多 8 扇区、有界超时、FLUSH；
  block ABI 只允许 files 服务。FatFs/路径/文件内容在 ring3。
- 文件 ABI v2：4096 字节消息、255 字节以内 ASCII 路径、LFN/目录、根相对路径，
  无 cwd/dot 路径/Unicode。文件不再限制为 4×24 KiB；大小 u32，保守 FAT32 上界
  0xfffffffe，实际受格式与可用磁盘空间约束。每会话 16 打开、全局 32 个 FatFs 对象锁（0020调整）。
- 内核为普通子程序分配独立请求/响应端点，绑定真实发送/接收 PID；files 用专属
  sys_file_session 枚举任务槽。端点 token 在一次启动内单调不复用；退出/abort
  清理端点，files 清理旧 PID 的打开实例和未提交保存。任务不继承 builder/块设备权限。
- 保存 staging 直接在磁盘，顺序 chunk、commit/abort；全局一笔保存，其他活客户端
  返回 busy，不能抢走 staging。延续 temp/journal/backup 恢复；正常同步重启已验证，
  不承诺任意掉电事务原子性。hello.elf 只在缺失时注入。
- ELF 校验在用户态，文件装载持有读锁并按段/页读取，无整文件 RAM 缓冲；零填 BSS，
  W^X/范围/入口/页预算检查，失败关闭/abort。只读启动模块仍有 128 KiB 限制，
  工作盘 ELF 不受该限制。SDK 的 AArch64 编译检查不代表第二 ISA 移植。
- sup> 提供 ls [path]/cat/stat/rm/edit/filetest/sync/exec-file/exec-driver/spawn-file/mkdir/mv；
  既有 exec/spawn/wait/kill/stats/primtest/elftest 保留。files/supervisor 是受保护
  bootstrap 服务，kill 拒绝；普通程序可被 kill 或前台 Escape 取消并 wait。
- 编辑器仍 8 KiB，正文原样保存；终端按空格分词，无引号。argv 最多64项/每项
  255字节，argv/env/cwd共享4页startup；32页可用栈另加guard。
  cat分块输出；SDK路径可有空格，终端暂不能输入带空格的路径。
- E08-2 newlib适配已连接真实文件/目录/临时文件/errno、动态sbrk堆、受限
  posix_spawn/waitpid/stdio/pipe。exec-driver显式授权，不继承给孙任务；
  普通程序不能创建子工具。最终5组runtime检查及完整集成回归通过。
  限制见e08_runtime.md；不是完整POSIX，无fork/mmap/墙钟/符号链接/权限位。
- stat/fstat返回真实SFN目录项映射身份，root inode=1、其余16位编号不复用，
  每次服务生命最多65534个非root身份，耗尽失败；rename/保存保持身份。
- GNU Binutils 2.47的as/ld/ar/ranlib/strip为工作盘XOS可执行Seed，真正客体产出
  目标文件/静态库/ELF，strip后重启可执行。另4个工具仅静态检查，不冒称客体验收。
  使用方法与限制见e08_binutils_seed.md；无TLS/动态插件，捆绑zlib静态链接。
- 显式离线 work_disk.py 可 mkdir/import/export，拒绝覆盖目标；运行时文件/装载
  都在客体，不由宿主代执行。

## 当前E08-2/3 最终证据

构建5276ff16bb6470b0；源码SHA256：
5276ff16bb6470b0b5dd25b3516e819929e617a8f74147e0205440ed4085a110。
xos.img SHA256 7f4e361efed1c8b40470b30bfdb859d7d95c7bea13cfbfa3504949f82b28513a。

- make smoke：79组通过，包含5组E08-2及旧74组；另7份许可材料检查通过。
- 显式binutils_smoke：7组通过，32次实际命令，包含两轮完整链路、索引前后检查、
  同文件保护、汇编/链接错误、插件拒绝、源码逐字节保留、每步资源复原和同步重启。
- E08-3压力测试（2026-10-24，5276ff16）：S0/S1/S3/S4通过；S2的34成员archive
  final `ld` 报成员unknown architecture（首次21.o，probe中0.o，首个失败成员不稳定）。
  不是对象生成错误；host对象/archive有效，guest `ar t`和`ld -r`可读。E08-3压力
  不算全绿，S2当时是E08-4 archive/GCC前的blocker；0017已定向修复，见上。报告：
  `docs/reports/e08_3_stress_report.md`、`build/e08_3_stress_combined.json`。
  生成ELF及stripped ELF均输出seed chain并退出42，宿主readelf/nm仅静态核对。
- make build同源重建完整manifest相同，193个产物、260个源码哈希均核对通过。
- Seed构建指纹47ddd3071e2ad7f69b8b903c51b491aa59d81ed96e173fb0f506341248af0a9e，
  目录.cache/xos_seed/binutils/build/下，manifest SHA256
  1673edded076b3a8e001fc538ec52a452c38d4f2a7a115e7190fbdc2f69f3ef0。
  SDK快照765f556c…绑定实际CRT/库哈希，虽全局build_id早于最终测试文件，逐项与
  当前SDK链接输入一致并由测试核对。没有宣称GNU独立全清理重编的位一致性。
- 原始证据：build/manifest.json、各正式smoke_report.json、binutils_smoke_report.json、
  e08_rebuild_check.json、license_report.json、binutils_*静态检查与串口日志；关键哈希
  保存在0015。as_preflight_report.json保留早期TLS失败，不是最终gate结果。

不能将下列E08-1历史基线哈希当成本轮最终版本。

## E08-1 完整基线证据

构建 ID：f3c198eb5044cb15；源码 SHA-256：
f3c198eb5044cb15beb1883e6809cde4cc3db52294d0004335e75ec6616e9885。

- kernel.elf：5774a6414ff5ad9250f301223a0bbe7c54b736c4551caf7f849db0c03fbe4820。
- kernel.bin：274460 字节、537 扇区；972776c5c3735954ad2fe45894c0bdcf9997a9f91d6758ec18888061691e3026。
- xos.img：74b77c85018cc8a88f695836982299b5cf70de594f71e72f4e5f2acff77e1931。
- 磁盘专用 e08_probe ELF：277808 字节；fed961ca05f96725403f12823994304e2a15d046b2ae268ed501e8ab5b7887fa。
- make smoke：6+18+12+13+8+4+1+3+9 = **74 组通过**，另 7 份许可证材料检查通过。
- 新 gate：两种 FAT32 容量、大 ELF/BSS、子进程路径/目录/改名/空格名字、256 KiB
  流式保存/逐字节导出比较/双启动、非法 ELF 回滚、并发会话、保存冲突、取消清理、
  65536 页上限和全部页表回收。旧 FAT16、物理满盘、ELF ASan/UBSan 与通用代码
  AArch64 编译检查继续通过。
- 最终样本：512 MiB/2 GiB 盘原始 ATA 读 6.52/6.74 MiB/s，经文件服务读取
  3.96/4.14 MiB/s；65536 页压力含撤销约 0.396 秒。固定 TCG/缓存下单次样本，
  不是 GCC 性能/冷缓存/真机证明。支持继续保留预载方案，尚未测真实 Seed 峰值。
- 同源码重建完整 manifest 与全部产物哈希相同，所有源码绑定核对通过。
- 已查看 build/e08_2048_screen.png：重启后 verify 输出 BSS/path/stream/sync=ok、退出 0。

原始证据在 build/manifest.json、各 *_smoke_report.json、e08_storage_smoke_report.json、
e08_rebuild_check.json、license_report.json、e08_*_serial.log、截图。关键结论及哈希
亦保留在 0012，清理 build/ 不会丢失交接结论。工具版本仍为 GCC/G++ 16.2.0、
Binutils 2.47.20260726、NASM 3.02、QEMU 11.1.2。

## 许可证与未来图形方向

自研新代码 Apache-2.0；历史 MIT 基线/声明保留，第三方原条款保留。管理见
licensing.md、licenses/components.json、LICENSE/NOTICE；SDK 实际携带并记录哈希。
本次许可确认与材料检查记录见 work_log/0014_license_management.md。
newlib 为多来源条款，不能统一标为 LGPL。当前库逐成员许可证追溯尚未完成，
不因材料检查通过就声称法律/组件审计全部完成；未来 GNU Seed 分发另核实际条款。

用户于2026-10-24确认Qt为GUI主线、SDL为次选，取代此前SDL优先方向。
xos_plan.md v0.5已新增E13–E20与G01–G10：运行基底、显示/输入、QtCore、
QtGui/QPA、Widgets、无界面QML、软件Quick、集成/试用分别验收。
版本/feature/线程与资源预算按阶段冻结；Qt原生重建另验，不作为首窗前置。
窄OS服务与用户态Qt/SDL适配分开，不绑定固件/ISA；尚未引入Qt或开始GUI实现。
本组仅文档修改，责任已结束；交接见work_log/0016_qt_gui_plan.md。

## 下一步：E09交付/试用；Qt GUI 扩展已纳入计划

先读reports/e08_acceptance.md、work_log/0022_cpp_seed_acceptance.md、e08_cpp_seed.md。

1. E09尚未开始：准备可交给朋友的镜像、独立工作盘、版本化SDK和真实上手说明；
   公开分发前补GNU对应源码/许可材料核对，不能把本地材料检查当完整发布审查。
2. 后续压力继续专人负责，使用0022正式派生G++/目标库及0020修复C/binutils；
   不复用含已暴露bug的原始工具。已有功能测试不无变化重复运行。
3. Qt主线/SDL次选仍按v0.5的独立阶段，当前未开工；系统重建和自举也另行验收。

当前已有受限GCC/G++及目标标准库基础设施；尚无完整POSIX/完整C++标准库、动态链接、UEFI、SMP、服务重启、sysroot 只读授权或任意掉电保证。
E08当前受限功能范围已完成，O11–O13按0022固定静态配置通过；其他O条目不自动改标。
