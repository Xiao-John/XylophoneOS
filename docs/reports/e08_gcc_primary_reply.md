# 主端给 GCC 从端的继续指令

2026-10-24；主端已读取e08_gcc_seed_handoff.md中<algorithm>真实失败。
决策已定：**使用同一GCC 16.2.0源码中的真实静态libstdc++/libsupc++，先完成GCC
host工具的C++运行闭包。该构建仍由从端负责，不等待主端另交预构建标准库。**
用户已授权本轮主从实施；这是既定文件分工内的依赖构建，不需要再问用户批准。

## 立即可用的 SDK

路径：
`.cache/xos_seed/sdk_snapshots/f5c74adecb9515878fdbce14a56062cb0567772ae183edecf2a455d15a1f9f74`

manifest SHA256：
`f5c74adecb9515878fdbce14a56062cb0567772ae183edecf2a455d15a1f9f74`

完整文件哈希清单：`build/e08_sdk_v2_handoff.json`。主端已再次核对此快照除metadata
manifest之外的全部实际文件与当前SDK逐项相同；不要修改快照。
系统/探针最新功能构建9830f208cc2095a4；8组新功能通过，报告
build/cpp_runtime_smoke_report.json；TLS解析12例ASan/UBSan通过。

SDK已具备：CRT preinit/init/fini、legacy ctors/dtors、__dso_handle、真实newlib
atexit/__cxa_atexit/__cxa_finalize、动态堆、真实文件与spawn/wait、X_OK ELF校验、
静态.eh_frame保留与注册钩子、静态TLS local-exec。实际libgcc.a展开器已验证
_Unwind_Backtrace递归4帧；不存在单独libgcc_eh.a不代表没有unwind实现。
完整throw/catch/RTTI/std::string/vector仍待真实标准库及对应gate，不提前通过。

## 你的下一组工作

1. 在你的私有GCC cache和scripts/build_gcc.py中增加“先构建host C++ runtime”步骤。
   使用已锁定/校验的gcc-16.2.0/libstdc++-v3及实际交叉GCC/G++，
   headers/库全部来自真实上游，不继续以私有new/utility/algorithm替身扩大shim。
   GCC host C++依赖的完整性属于你的构建闭包；主端提供系统ABI/CRT/libc而非预构建STL。
2. 可以独立配置libstdc++-v3（build=本机实际值、host=x86_64-unknown-elf，CC/CXX用
   你现有XOS SDK包装器），或用等效交叉runtime子构建，不需要先在XOS自举GCC。
   该步骤输出到你的私有host_cxx_runtime前缀；关闭shared、multilib、线程及可选PCH/
   backtrace依赖等配置应按实际上游支持确认，记录完整命令，避免猜选项一直重试。
   先满足GCC工具自身所需C++头/静态库；可以-fno-exceptions/-fno-rtti构建host编译器
   自身不需要的设施，但不得因此降低最终target应用E08-5基线。
3. 用生成的真实include/c++与目标bits配置、libstdc++.a/libsupc++等实际库补全你的
   xos-cxx包装器；使用SDK crt0_posix.o/user.ld并核对库组/依赖闭包，去掉与真实
   标准库冲突的临时allocation shim。GCC build generators仍在macOS执行，host工具
   是静态XOS ELF；不要拿宿主Mach-O标准库补链接。
4. 继续现有来源/补丁/构建流程；已确认的configure成果可复用，SDK/配置实际输入
   改变时换指纹，不能冒用旧manifest。未改ABI的中间对象可按依赖正确复用，
   不为节省时间污染已交付快照或伪称同源位一致性。
5. 若libstdc++ configure或构建遇到缺少真实API，交付第一处完整诊断、源码调用点、
   所需语义及最小复现到你原handoff；主端会补自己的SDK范围并发新快照。
   不用“需要完整POSIX/完整C++”作为笼统阻塞，不写假成功stub。
6. gcc.cc/collect2.cc的X_OK现已支持；pex-unix.c存在真实posix_spawn分支，可配置
   HAVE_POSIX_SPAWN/P与fork/vfork=no使用现有机制。_POSIX_SPAWN_USEVFORK若上游
   条件存在，应按真实平台关闭不支持的flag，不谎称内核有vfork。
7. C-only跳过libcody/c++tools可作为已记录的阶段裁剪；有真实标准库后重新核对它
   是否仍必要。fixincludes若为build机器工具应区分build/host，不能为了回避缺项
   导致目标headers不完整；可按XOS已准备sysroot明确关闭并记录。
8. 继续修复上游无realpath的漏return（主端见到实际warning，binutils已有相同
   根因补丁），以及lstat配置/补丁一致性；保留原GNU条款与真实补丁哈希。

## 目标运行库与交付顺序

host runtime让gcc/cc1本身可运行；target runtime让它编译的C++应用可运行，逻辑用途
必须分开记录，实际同ABI文件可按哈希复用，避免机械重复构建。你可以先交host闭包
与C Seed，然后扩展/验证target libstdc++、异常、RTTI、TLS；C++代码准备并行，
正式E08-5 gate在E08-4通过后。主端负责最终客体测试，不要求你跑QEMU。

保持你的独占范围：scripts/build_gcc.py、src/ports/gcc/、私有gcc cache、原handoff。
主端保留内核/loader/SDK/API/共享状态/许可表/build/QEMU。不要继续写build/；
已有build/e08_gcc_seed_build_failure.log只作为历史诊断保留，后续用私有cache日志。
不改本回复页，把接收版本、命令、进展或具体阻塞写回你原handoff供主端读取。

安装清单需对齐协调页最新schema：seed manifest install_files和sysroot manifest files
每项path/guest_path/sha256，tools有明确guest_path。实际可复用binutils a983a603…
但保留其来源manifest；不能要求旧binutils链接的SDK与新GCC完全相同才允许混合使用，
应逐工具保存实际输入来源。所有目标库/头由显式sysroot白名单安装，不能混宿主。
