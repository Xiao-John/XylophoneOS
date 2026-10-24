# 0019：E08-4/5 主端实施

2026-10-24；状态：进行中，阶段gate尚未通过。
用户已启动从端并授权主端开工。主端负责内核/loader/ABI、SDK、集成、共享文档
和最终验收；从端独占GCC构建/ports/cache。Luna任务和准确文件范围见协调页。
不重跑已有压力轮次，后续压力由专人负责。

## 当前实现

- luna_runtime：POSIX main前CRT preinit/init，正常exit时C++析构/fini、可用时注册与
  注销静态.eh_frame；独立构造/TLS并存任务探针与功能测试。
- 主端：user.ld保留init/fini、异常展开信息与PT_TLS；用户态ELF解析静态TLS模板，
  x86_64 loader后端布置variant II，内核仅设置/切换任务线程指针。
- luna_cases：C/C++ Seed功能测试与fixtures，等待从端正式安装manifest对齐。

静态TLS arena为[0x5fe00000,0x60000000)，ELF LOAD与堆不进入该区；模板上限
1MiB、对齐最多64KiB，拒绝坏范围/重复TLS/初始化模板与LOAD不一致等。
PT_TLS解析仍在用户态；模板与TCB按页映射计入任务页配额、失败统一abort。
sys_process_tls=35仅允许构造者为自己owned、building子任务设置已映射RW的TP，
内核不解析ELF；AMD64恢复FS base在arch/x86_64，通用代码不包含寄存器操作。
仅静态local-exec，无动态模块/动态TLS/DTV、线程或第二ISA启动。

## 已运行与待验证

- make build（中间a04a7890fa20168f）成功，尚未含最终并存TLS探针。
- 新TLS解析12个确定性用例以宿主Clang ASan/UBSan通过，命令：
  clang++ -std=c++20 -fsanitize=address,undefined -fno-omit-frame-pointer -g \
  -I src/user/include -I src/shared/include tests/static_tls_cases.cpp \
  src/user/loader/elf.cpp -o build/static_tls_cases
  build/static_tls_cases
- 真实CRT/TLS客体功能测试、异常/RTTI/完整libstdc++、GCC C gate尚未运行。
  新SDK将在主端真实功能验证后固定快照交付从端。

不得把运行基底补齐记为GCC/G++已完成。localpilot与日常盘不碰，未提交/推送/读凭据。

## 本组运行基底交付（阶段仍在进行）

最终本组功能构建 `9830f208cc2095a4`；源码SHA256 `9830f208cc2095a4a0511002c1b3636e68864ad524f117b32d0b94da65665687`。
xos.img SHA256 `c1bb2db75f007d813f6fa3d9516fa7184236af8852da40805e1f49a0669ecdbd`，kernel.bin SHA256 `55fac73b4671d7772453b0a3c352a3a137d10de0748a7951886c6cb0948576e2`。
探针SHA256 `481fb55b81f3a503bde6eb2aec2c0a6c7e27be3f2bbd92876f43d61cce729232`。完整8组功能报告build/cpp_runtime_smoke_report.json，
串口build/cpp_runtime_smoke_serial.log，构建/测试日志e08_cpp_runtime_final_*.log。

新增功能验证：

1. 构造者sys35权限、arena范围、未映射TP拒绝，以及abort资源回收。
2. 客体拒绝4种畸形PT_TLS，页/任务/完成记录不变；宿主另12个元数据用例ASan/UBSan通过。
3. 实际GNU libgcc.a的_Unwind_Backtrace通过递归至少4帧，证明静态frame注册与查找；
   不是throw/catch或RTTI证明。原审计说libgcc_eh.a缺失，不代表libgcc.a没有展开器。
4. GCC gcc.cc/collect2.cc真实调用access(X_OK)查找工具，现libc按同一ELF解析器
   校验读锁保护的文件；可执行ELF/目录通过，普通数据EACCES、缺失ENOENT。
5. 两个并存任务A/B，TLS模板8字节、总8272字节、对齐64，初始化/.tbss/跨页、
   yield/PIT隔离正确；各自wait正常退出0。
6. preinit/init/全局构造、main、全局析构/fini顺序正确。
7. 资源基线与结束均[130355,2,0]，不以旧基线数值代替当前版本。
8. 修改的通用ELF/loader通过AArch64仅编译检查（不是第二ISA移植），80个实际
   kernel/shared/user及构建配置源码哈希与当前manifest一致。

首次probe曾失败：当前交叉GCC发出legacy .ctors而非.init_array，漏掉全局构造。
真实日志/失败报告保存在build/cpp_runtime_legacy_ctors_failure.json，已补legacy
ctors逆序/dtors正序并过滤sentinel；随后的完整功能probe通过，不隐去失败过程。
后增GNU回溯和权限/坏TLS用例后才执行最终8组，未为无变化重复测试。

SDK v2已独立复制到
`.cache/xos_seed/sdk_snapshots/f5c74adecb9515878fdbce14a56062cb0567772ae183edecf2a455d15a1f9f74`，
manifest SHA256与目录名相同。全文件清单build/e08_sdk_v2_handoff.json；与最终SDK
逐文件比较，除manifest的全局build_id metadata外所有实际链接/头文件输入均相同。
此快照含真实CRT/运行ABI，不含libstdc++/libsupc++，不可冒称C++ Seed已验收。

## 从端阻塞与主端决定

从端报告GCC C本体<algorithm>缺项，初期new/delete shim不足。
主端决定同一GCC 16.2.0源码的真实静态libstdc++/libsupc++由从端在已归属构建脚本
和cache中先构建，供host GCC/cc1执行；主端继续负责运行ABI/CRT/libc。
正式回复为reports/e08_gcc_primary_reply.md，包含可用SDK、完整哈希和继续步骤。
两边不相互等待“完整C++阶段已通过”，也不把host runtime当target C++验收。

Luna的CRT/探针和Seed功能用例均已交付，暂无其活跃编辑占用；主端继续保有
build/、ABI与共享文档，等待从端实际Seed或精确运行缺项。新功能gate代码已静态
语法核验，真正GCC/G++ gate因Seed未交付仍未运行，E08-4/5没有通过。
未重跑make smoke/旧binutils压力/长soak/重启或重建一致性；压力测试由专人负责。
SDK使用GNU libgcc实际展开器，许可证/例外沿现有GNU链接输入登记，未新增依赖版本；
从端正在新增GCC/GMP/MPFR/MPC材料，由主端收到正式交付后再集成组件表。
