# E08-4/5 分工与交付入口

2026-10-24；最新：0020 C Seed功能gate通过，Luna均交付；以下启动分工保留作历史，当前无剩余编辑占用。
主负责人是当前主agent；另一agent为工具链构建协作者。执行时主agent在本页
登记实际参与者、范围与状态，不因有prompt就假设任务正在运行。

| 负责人 | 范围 | 首批交付 | 后续交付 |
|---|---|---|---|
| 主agent | ABI/内核/loader、用户运行基底、构建集成、许可表、共享状态、最终客体gate | SDK与进程/运行库合同；E08-4集成 | E08-5机制与最终结论 |
| 主agent的luna_runtime | 主agent明确移交的libc/SDK与探针文件 | 按真实GCC调用补缺 | 按真实C++调用补缺；不改内核 |
| 主agent的luna_cases | gcc/cpp_seed_smoke与各自fixtures | C功能gate实现 | C++各设施gate实现 |
| 另一agent | build_gcc.py、ports/gcc、私有gcc cache、独立交接页 | C Seed构建与实际依赖闭包 | G++与目标运行库构建 |

两份可直接执行的prompt：

- [主负责人](prompts/e08_4_5_primary.md)。
- [工具链协作者](prompts/e08_4_5_secondary.md)。

## 先后关系

1. 主agent登记范围、给出SDK/权限/运行库合同；另一agent可先准备来源、依赖与配置。
2. 主agent与Luna补有实际证据的系统缺项；另一agent以不可变SDK在私有cache构建。
3. 交付C Seed → 主agent真实客体C gate → 正式E08-4结论。
4. C++准备可提前并行；交付G++/运行库 → 主agent完成异常/RTTI/TLS机制与各项gate
   → 正式E08-5结论。不能因编译器本身需要C++运行库就把E08-5提前标完成。

E08-5沿用pre1既定范围：基础容器/string、异常、RTTI、TLS必须；iostream可选。
无线程时仅验证实际任务TLS语义，不声称验证线程并发。关闭这些设施的产物只算子集。
E08-6集成与E11自举仍单独验收。Qt不进入本轮。

## 冲突和版本控制

- build/与SDK导出、最终QEMU仅主agent使用，不并发构建/清理。
- 另一agent构建缓存独立于binutils；SDK内容固定，实际输入哈希绑定，改ABI必须换快照。
- 独立交接页为reports/e08_gcc_seed_handoff.md、e08_runtime_handoff.md、
  e08_cases_handoff.md；此页/state/decisions由主agent统一更新。
- 新依赖许可材料由协作者收集，根组件表由主agent集成；不因材料齐全冒称完整审查。
- 当前修复基线见0017：b1ded17e673ccffc，新binutils Seed a983a603…；旧47ddd307…含bug。
- 只做新功能gate与实际修复的对应回归；已有全量和压力测试不重复，后续压力由专人负责。

## 启动后填写

实际人员/占用：主agent负责内核/loader/ABI、构建/SDK、共享文档和build/；
luna_runtime负责main_entry.cpp/libc_runtime.hpp/cpp_runtime.cpp、
cpp_runtime_probe.cpp和tests/cpp_runtime_smoke.py；newlib_syscalls暂主端保留；
luna_cases独占tests/gcc_seed_smoke.py、cpp_seed_smoke.py、fixtures/gcc与cpp；
从端独占scripts/build_gcc.py、src/ports/gcc/和私有gcc cache，已开始独立交接页。
当前SDK合同：待主agent冻结；0017快照仅为已知起点，不预设能满足GCC。
协作者首批缺项/交付：未提交。
E08-4 gate：passed（0020，82ffcecab8ccbcce，4组/15命令）。
E08-5 gate：not_run。

## 主端输入合同 v1（进行中，供从端读取）

- 主端已启动luna_runtime与luna_cases，无其他同范围代理；主端独占build/和最终QEMU。
- 0017 SDK f1876914…可作为C阶段初始依赖/配置输入，真实API按e08_runtime.md。
  GCC host C++头/静态libstdc++/libsupc++需由从端build_gcc构建交付；当前SDK尚无。
  不必等待完整E08-5才准备其host运行闭包，可关闭编译器自身不需要的异常/RTTI，
  但这不改变目标应用E08-5基线。若无法按此构建，交付精确configure/链接缺项。
- 主端正在补CRT preinit/init/fini与.eh_frame保留/静态注册，随后发布新不可变SDK。
  从端现在可下载校验来源、构建依赖/配置，不把当前CRT当最终构造/异常支持。
- 目标安装映射：install/usr/... → guest /usr/...；driver /usr/bin/x86_64-elf-gcc
  和g++，cc1/cc1plus保留GCC libexec层级。sysroot宿主安装目录显式交付，客体/sysroot。
  目标程序XOS CRT+user.ld+libxos+newlib+libgcc，目标默认链接策略/搜索目录需从端给出。
- manifest沿用binutils的sdk_manifest、sdk_manifest_sha256、sdk_input_hashes、tools。
  另交付安装白名单（relative path + SHA256 + guest absolute path）、target sysroot白名单，
  host工具依赖库与target库用途分开；测试不得从宿主系统路径补目标文件。
- driver默认临时文件顺序调用，不要求-pipe；真实posix_spawn/waitpid可用，
  waitpid仅指定正PID阻塞。无fork/execve/信号语义；pex按实际源码选择/最小补丁。
- 构造权当前不继承；collect2需要再spawn时先交真实调用树与需求，由主端定最小机制。
- E08-5主端将支持静态TLS local-exec：x86-64 variant II，每任务独立块与FS base，
  不支持动态模块/DTV，明确拒绝动态ELF；具体布局与SDK v2一起发布后再冻结。

## 新SDK交付 v2（可用于从端构建）

主端真实CRT/TLS功能验证通过：构建10306f6414f8d488，报告
build/cpp_runtime_smoke_report.json，5组新功能通过；TLS解析12例ASan/UBSan通过。
不可变SDK：`.cache/xos_seed/sdk_snapshots/f5c74adecb9515878fdbce14a56062cb0567772ae183edecf2a455d15a1f9f74`，manifest SHA256 `f5c74adecb9515878fdbce14a56062cb0567772ae183edecf2a455d15a1f9f74`。
实际完整文件清单/哈希：build/e08_sdk_v2_handoff.json；CRT、库、user.ld与头全部复制。
此SDK不含libstdc++/libsupc++/libgcc_eh，需从端构建交付；不是完整E08-5验收。

- 正常C/C++ main用crt0_posix.o；user.ld已保留preinit/init/fini及legacy ctors/dtors、
  .eh_frame（__eh_frame_start+0 terminator）、.gcc_except_table、静态TLS。
- 不需要crtbegin/crtend重复提供__dso_handle或重复注册，当前SDK运行时已提供
  __dso_handle与可用时的__register_frame/注销钩子。必须用实际输出验证最终链接策略。
- 静态TLS local-exec，AMD64 variant II，template≤1MiB、align≤64KiB，FS:0=self。
  动态TLS/DTV、动态ELF与线程不支持。内核在用户入口前恢复FS，不需libc自行设FS。
- access(X_OK)现在按受支持ELF元数据真实校验，目录允许遍历；普通数据返回EACCES、
  缺失返回ENOENT，已客体验证。GCC gcc.cc/collect2.cc的真实工具查找路径需要它。
- SDK headers与libxos包含新进程sys35和TLSloader，任何从新SDK链接的driver/工具
  继续静态绑定本快照。后续若补运行缺项，发布v3而不修改此快照。
- driver仍仅直接子构造权；若collect2必须再spawn，报调用树后主端补最小授权。
  可以先验证上游可用的直接GNU ld路径，不能把ld改成宿主执行。
- 新功能gate安装白名单schema已由Luna落实：主端测试需要seed_manifest.install_files
  和独立sysroot_manifest.files，每项path/guest_path/sha256；tools项提供guest_path。
  --seed-root为你的install目录，--sysroot-root为实际目标sysroot根，路径显式传入。

请从端读取本节，更新自己的handoff为已接收v2或记录具体阻塞；不需等完整C++ gate
才构建C Seed。需要的GCC host C++头/库属于从端构建闭包，主端提供运行ABI与SDK。

### 主端看到的从端构建诊断（不越界修改）

从端740c2ea8…/build.log已出现libiberty/unlink-if-ordinary.c调用lstat未声明，
及lrealpath.c control reaches end警告。GNU GCC复用libiberty时需按真实平台处理，
参考binutils已有最小no_symlink与lrealpath回退修复；不要忽略该未定义返回行为。
主端不修改从端文件或cache；由从端纳入自己的来源/补丁指纹并交付。

### 展开器实测补充

现有宿主交叉编译器实际libgcc.a已包含_Unwind_Backtrace/_Unwind_RaiseException、
_Unwind_Find_FDE与__register_frame，不能由“没有单独libgcc_eh.a”推出缺少展开器。
主端新增probe链接实际libgcc.a，真实XOS中通过递归4帧的_Unwind_Backtrace，
证明.eh_frame注册/查找/展开链可工作（70e3e95c4c477322，新增第6组功能）。
这不是C++ throw/catch或libsupc++/RTTI验收，仍需从端C++运行库和真实C++ gate。
可优先复用实际版本匹配的libgcc展开器，避免重复移植一套unwind实现。

## 从端等待的正式回复

从端<algorithm>阻塞已收到，继续决策见[主端回复](reports/e08_gcc_primary_reply.md)。
从端负责同GCC源码真实host libstdc++/libsupc++构建，不等待主端交预构建STL；
主端已交可用SDK v2。用户可将此文件路径转给已等待的从端继续执行。

## 0020 当前占用

从端C Seed已交付c3b803762179…（stable manifest src/ports/gcc/seed_manifest.json）。
主端保有tests/gcc_seed_smoke.py、cpp_seed_smoke.py及新诊断/集成脚本和build/；
Luna preflight独占scripts/seed_preflight.py、tests/seed_preflight_cases.py与独立报告；
Luna ABI独占tests/fixtures/cpp_abi/、scripts/build_cpp_abi_probe.py、tests/cpp_abi_smoke.py。
从端GCC源码/配置/缓存不在本组修改范围，原SDK v2快照不改动。

### C Seed 首次启动失败与最小接管范围

用户确认从端已完成；主端接管新增GCC lrealpath修复补丁与独立relink脚本范围，
不修改原GCC源码树、原构建对象/缓存或旧manifest。首次gcc --version在_free_r故障，
反汇编确认lrealpath仅ret。采用已验证同根因的strdup回退，复用已编译对象、
在独立relink目录重链接工具，逐项绑定输入/输出哈希，避免完整GNU重编。

### 0020接收进度与边界

Luna preflight/ABI交付已冻结，主端接管其文件；用户确认从端完成后，主端追加了
0007 lrealpath修复、独立relink与GNU许可材料登记。原始Seed稳定manifest保留，
其gcc不能直接用于正式验收；实际派生入口为relinks/open_capacity_fix/seed_manifest.json。
每会话16-open、FatFs全局32锁为真实GCC/BFD链接缺口调整；SDK v4为
1ba7c52c568725cac63c4a9e603aabd61f30e00db430ca0e5afb4fcfee956490。
目标C++库仍未交付；下一步需同版本G++/cc1plus、真正target libstdc++/libsupc++
及异常/RTTI/TLS配置与哈希，不得复用no-exceptions/no-rtti的host库冒充通过。
探针交付合同见reports/e08_cpp_abi_handoff.md，C工具使用见e08_gcc_seed.md。

0020最终C gate在82ffcecab8ccbcce通过4组/15命令，详见work_log/0020_seed_integration.md。
E08-5仍not_run，目标运行库not_ready；已结束本组编辑占用，后续组重新登记。

## 0021：E08-5新一组

最新占用以state.md的0021段为准；从端新prompt为prompts/e08_5_secondary.md，
现仅完成任务落盘，未确认外部从端已启动。优先分批交付target运行库以解锁ABI，
再交G++/cc1plus；主端同时准备TLS析构与E08-6独立测试。不重跑旧功能/压力轮次。

### 0021主端新运行基底已交付

SDK v5：.cache/xos_seed/sdk_snapshots/3a302b5cd7e1cdab0f594b0d16d7ca92b753fec7b2efcc6347b01e5a69542edd，
manifest SHA256同目录名，系统f40c9a254b5433d7。实际TLS ABI `__cxa_thread_atexit`
及强exit已在客体通过main return/显式exit、LIFO、析构中新注册、TLS先于global/
fini、逐任务资源回收。C编辑/重新构建/正常重启增量在82ffcecab8ccbcce已通过，
保留旧镜像与manifest；不是E08-6全部通过。目标库/G++待交付，E08-5仍not_run。
Luna均冻结文件，主端统一构建/新测试完成，没有剩余子代理编辑占用。
外部从端prompt已更新优先v5，仍未确认其已启动；不可猜测任务正在执行。

## 0022收口

从端A/B已接收，主端完成独立TLS回退配置修复与G++ lrealpath派生重链接。
ABI六项、原生G++4组/14命令、C++编辑/正常重启4项/18命令通过，结合既有C增量
判定E08当前受限功能闭环完成。综合报告reports/e08_acceptance.md，过程0022。
所有编辑占用结束；原始A/B/SDK不覆盖，正式安装入口e08_cpp_seed.md，不重跑旧
压力。下一组重新登记范围，当前不启动GUI/重建/自举。
