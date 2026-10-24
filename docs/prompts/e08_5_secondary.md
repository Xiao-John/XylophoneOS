# E08-5 从端执行 prompt：先交付目标 C++ 运行库，再交付 G++ Seed

最新输入：主端已真实验证TLS正常退出顺序并发布SDK v5：
`.cache/xos_seed/sdk_snapshots/3a302b5cd7e1cdab0f594b0d16d7ca92b753fec7b2efcc6347b01e5a69542edd`，manifest SHA256同目录名。
现在开始构建优先使用v5；已用v4编好的兼容对象保留实际输入证据并可增量复用。
主端系统f40c9a254b5433d7，TLS return/exit两路径通过；C编辑/重启部分通过，
目标C++库/G++尚未交付，不能标E08-5通过。下文v4是历史可用输入。

你是工具链构建从端；主负责人是当前主端。现在开始 E08-5，目标是尽早交付可验收
产物，使今晚能进入 E08-6 集成验收。时间目标不改变异常/RTTI/TLS必需基线。
先按AGENTS.md顺序读Discipline/state/xos_plan，再读0020工作记录、e08_gcc_seed.md、
reports/e08_gcc_seed_handoff.md及reports/e08_cpp_abi_handoff.md。

## 独占范围和协作

你独占 scripts/build_gcc.py、可新增scripts/build_target_stdcxx.py与scripts/build_gxx.py、
src/ports/gcc/构建配置/新增补丁和 .cache/xos_seed/gcc/ 下新建e08_5私有工作目录。
不要修改原已验收Seed、旧构建对象、SDK快照或原始manifest；可复用明确哈希绑定的
兼容对象，重新链接时记录真实CRT/库/对象输入。不要写build/、内核/libc/loader、
共享tests、state/decisions。唯一共享输出入口为docs/reports/e08_5_secondary_handoff.md，
明确每批状态/命令/输入输出hash/失败调用点。主端统一集成、SDK与QEMU，不在从端跑客体。
主端Luna负责指定ABI运行时与独立E08-6测试；不碰你的GNU构建目录。

## 已可用输入

- E08-4已通过4组/15命令，最终系统82ffcecab8ccbcce；C profile直接GNU ld，
  collect2未验收，不要为G++默认恢复collect2或扩大权限。
- SDK v4绝对位置为当前仓库/.cache/xos_seed/sdk_snapshots/1ba7c52c568725cac63c4a9e603aabd61f30e00db430ca0e5afb4fcfee956490，
  manifest SHA256同目录名；读取后冻结，不就地改写。主端若补ABI将另交新SDK，
  GNU源码/前端对象尽量继续构建，最终重链接即可，不因换CRT全部从头编。
- 已验收派生C Seed：.cache/xos_seed/gcc/relinks/open_capacity_fix/seed_manifest.json。
  原始src/ports/gcc/seed_manifest.json仅作历史来源，原gcc仍有已暴露bug。
- 必须纳入0007 lrealpath修复（旧私有source未必已应用，逐补丁实际核验）；不要让
  旧apply_patches的一次性判断跳过新增补丁。O_NOCTTY已由v4 libc支持。
- 真实host工具依赖闭包在.cache/xos_seed/gcc/stdcxx/prefix，采用-fno-exceptions
  -fno-rtti，仅供GCC/cc1自身，不能作为本批target库。libgcc.a实际含GNU unwinder。
- 文件上限16/session、32全局锁；静态TLS local-exec variant II、FS:0=self；
  无动态TLS/DTV/线程。XOS CRT提供__dso_handle、ctors/fini、eh_frame注册，
  不默认再加入crtbegin/crtend。实际API缺项报告真实调用，主端负责修复，不写成功stub。

## 分批交付，避免所有人等待长编译

A（最高优先级）：用同GCC16.2源码构建独立 target_application_runtime。
真实libstdc++.a、libsupc++.a、完整C++headers+target config与libgcc，
启用异常和RTTI；静态、无线程、local-exec TLS，-mno-red-zone。不要把host关闭
exception/RTTI的配置缓存/对象混入。现有私有host构建可参考，但新prefix/对象必须分开。
先交一份runtime manifest及实际库文件；主端可立即用宿主交叉编译早期ABI探针，
这不冒称原生G++ gate。manifest严格采用reports/e08_cpp_abi_handoff.md接口，
ready只表示允许尝试，不表示通过；记录所有编译flag、源码补丁、SDK/libgcc哈希。
若完整libstdc++较慢，可先交真实libsupc++与具备的设施清单，不假报容器可用；继续构建A。

B（与A尽可能并行/复用）：构建可在XOS运行的g++ driver和cc1plus。
在新工作目录启用c,c++；不要套用会删掉C++前端所需组件的C-only补丁。
不必为了增加cc1plus重建全部GMP/MPFR/MPC与所有兼容C对象；可解释复用已有
真实host运行库（前端自身仍可无异常/RTTI），但目标A库不降级。最多按资源可承受
的make -j推进，保留日志，不盲目串行数十分钟也不破坏旧对象。
交付g++/cc1plus、install_files白名单、guest_path、完整hash和SDK绑定；guest安装
仍/usr/bin/x86_64-elf-g++和/usr/libexec/gcc/x86_64-elf/16.2.0/cc1plus。

C：完整A+Bmanifest与许可材料/来源。GCC16.2、GMP/MPFR/MPC固定版本不升级。
不构建Qt/GUI，不做GCC自举，不运行压力测试，不读取凭据/提交推送。
失败时尽快落第一处完整诊断、实际调用点、最小复现与可继续的独立工作；
缺SDK符号时不要空等，可以继续编译无需该符号的前端对象，等待最终重链接。

主端以runtime分批到货→独立ABI客体探针→原生G++设施gate→E08-6真实编辑/保存/
构建/执行/正常重启链路为顺序；从端不得自行把E08-5/E08整体标通过。

## SDK更新不阻塞长编译

主端已增加实际__cxa_thread_atexit/正常exit TLS析构出口并发布v5，v4不就地改。
这是静态应用用户库补缺，不改内核syscall/消息布局。可立即用v4编库/前端对象；
新SDK到货后，仅对真实依赖新头/ABI的对象增量编译，最终应用链接采用v5。
运行库manifest的sdk_manifest绑定探针/应用将要链接的SDK；若库对象用v4构建，
须在provenance.library_build_sdk保留v4完整hash与实际flags，不能悄悄抹掉实际输入。
主端prepare_gcc_seed.py新增--target-sdk显式选择应用sysroot，tool_runtime_sdks与
原G++/GCC manifest仍分别绑定工具自身的旧SDK；不要求为仅应用退出语义重编整个前端。
