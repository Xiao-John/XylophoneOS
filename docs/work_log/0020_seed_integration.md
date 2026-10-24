# 0020：接收 C Seed，安装预检、诊断与 C++ ABI 准备

2026-10-24。主端负责集成、SDK、实际客体验收和共享文档；从端已由用户确认完成。
Luna preflight 与 ABI 两组已交付并冻结，具体接口见 reports/e08_preflight_handoff.md、
reports/e08_cpp_abi_handoff.md。没有其他代理剩余编辑占用。

## 本组实现

- scripts/seed_preflight.py 与 tests/seed_preflight_cases.py：显式安装白名单/根路径、
  SHA256、FAT路径冲突、ELF/TLS/页预算检查；readonly，not_guest_test恒真。
  支持同一源文件映射不同guest alias，工具须精确选择路径，不能任取。
- scripts/seed_diagnostics.py 与 tests/seed_diagnostics_cases.py：真实wait结果、
  loader/权限/查找/编译/链接提示、实际-v子命令及include搜索；Configured with宿主
  来源不是运行搜索泄漏，分类提示不替代退出/故障结果。
- scripts/prepare_gcc_seed.py：组合GCC/binutils/完整SDK头和库，生成独立白名单及
  XOS静态C specs；构造和frame注册由XOS CRT负责，实际GNU ld直接链接。
  按GCC内置调用额外安装真实as的字节相同alias，不引入符号链接。
- tests/gcc_seed_smoke.py、cpp_seed_smoke.py：启动前preflight、显式exec-driver、
  失败无需等待不存在的wait、子命令诊断/宿主路径检查；离线导出须先关闭QEMU。
- scripts/build_cpp_abi_probe.py、tests/cpp_abi_smoke.py、tests/fixtures/cpp_abi/：
  容器/string、异常、RTTI、局部静态、非平凡TLS析构、多TU探针；显式真实target库
  manifest，缺库not_ready；交叉构建只算built_not_run，只有实际客体执行才算passed。
  这套提前探针不是正式原生G++ gate。

## 真实失败与修复

1. 原始gcc --version在_free_r触发#GP；反汇编lrealpath仅ret。新增GNU上下文保留
   原条款的0007回退strdup补丁。scripts/relink_gcc_seed.py只编译这一对象，再重放
   实际日志中的gcc/cpp/cc1最终链接，单独输出并绑定源码/对象/归档/编译器/SDK/host库
   哈希；避免完整configure/all-gcc重编。collect2未重链接且不用于当前profile。
2. 首版主specs用了%rename，真实GCC main specs不允许；改显式命名段定义。
3. libcpp/files.cc按O_RDONLY|O_NOCTTY|O_BINARY读源码，libc原先拒绝O_NOCTTY。
   XOS文件打开从不获得控制终端，接受该标志符合现有行为。此newlib无O_BINARY，
   GCC将其定义为0；最初同时加入O_BINARY导致主端编译失败，已移除，不造公开宏。
4. GCC内置as调用找不到安装名，补显式alias；首次真实汇编成功后，测试正则未容忍
   -v行首空格，修正匹配，并让诊断收集basename as命令。
5. 真正多文件+系统库链接暴露8-open后端限制；BFD cache至少10项，随后还需CRT/
   输出等句柄。每会话16、FatFs全局锁32，fd槽仍32；消息布局不变，耗尽仍真实失败。

原始稳定Seed manifest SHA256：
6c4bbcc5b2753a85e26e5b3ace6cb9ddec93f267021a4bd9c24334a9fc509ff7，
work c3b803762179aaf5929a6785295b852b014a4e54f0d0f091e1cc04262e8268bf。
SDK v2、原installed Seed和旧manifest保留。曾尝试在原build/gcc用make -n -W查询
collect2链接命令，但make求值触发生成器并失败；未采用其产物，没有完整原cache
逐字节未变证明，不能把只读意图写成已核验事实。独立派生只重放日志里的三条链接。

历史失败证据：build/gcc_seed_first_launch_failure.json、gcc_seed_specs_failure.json、
gcc_seed_open_flags_failure.json、gcc_seed_assembler_lookup_failure.json、
gcc_seed_trace_assertion_failure.json、gcc_seed_fd_limit_failure.json。主要根因与边界已
写在本页，即使build日志清理也能接续。

## 实际验证与边界

- Luna预检18个确定性用例通过；完整bundle readonly预检通过，不是客体执行。
- 主端diagnostics现9个用例通过；新增/修改Python语法编译和git diff --check通过。
- 实际host C++闭包声明为host_compiler_runtime、-fno-exceptions/-fno-rtti，ABI runner
  返回exit 2/not_ready且commands为空；没有拿host闭包当target库或启动QEMU假验收。
- C Seed功能gate在c67ae7433a017545通过4组/15命令；最终统一构建结果补在下节。
- 未重跑make smoke、旧CRT/TLS、历史binutils压力/soak；后续压力由专人负责。

## 许可与接续

新自研脚本/fixtures为Apache-2.0，移植GNU补丁保留GNU上下文条款。
components.json补登记GCC/host libstdc++/libsupc++、GMP/MPFR/MPC，实际声明复制在
src/ports/gcc/upstream/；补收各包LGPL/GPL和GCC Runtime Library Exception材料。
逐静态归档成员追溯与公开对应源码分发包核对仍未完成，不宣称法律审计完成。
localpilot与日常盘未碰；未提交/推送/读取凭据。

C gate之后继续从端G++/target libstdc++实际交付：exceptions、RTTI、string/vector、
TLS均为E08-5必需，不以host库关闭设施降低基线；先用独立ABI探针再真实原生G++ gate。

许可材料检查曾因从端三个自研兼容文件缺Apache标识失败，已补标识；材料检查最终
通过7份SDK声明及登记组件哈希。当前源码310项与最终build manifest逐项一致；
这不是完整重建位一致性或法律/成员审计。v4 ABI guard再验证exit 2/not_ready且
commands为空，证据build/cpp_abi_readiness_v4/。

## 最终验收与直接接续

E08-4 **受限C功能gate通过**；E08-5/E08-6与E08整体未完成。
最终系统构建 `82ffcecab8ccbcce`，源码SHA256 `82ffcecab8ccbccee5f901f106451ac1e05f1fbed40c68b3250d7a47fcac2776`；
xos.img SHA256 `bd5dd6d7342b42ce5904f0937675c3285f9058fa93d0568792b63e3d31530a8d`。

最终实际命令：

```sh
make build
python3 tests/gcc_seed_smoke.py --seed-manifest build/gcc_bundle/seed_manifest.json --seed-root . --sysroot-manifest build/gcc_bundle/sysroot_manifest.json --sysroot-root .
python3 scripts/license_audit.py
```

报告build/gcc_seed_smoke_report.json，串口build/gcc_seed_smoke_serial.log，日志
build/e08_gcc_final_build.log、e08_gcc_final_gate.log、e08_gcc_final_license_audit.log。
4组/15命令通过，逐条退出后资源均恢复[130342,2,0]：真实多TU与头文件、-c/-o、
归档rcS+ranlib、GCC直接GNU ld静态链接、客体执行；独立单TU的128位除/余数
确实引用__udivti3/__umodti3且客体执行正确；语法/链接/缺头/缺源码均非零；所有
源码离线逐字节不变。as/ld/cc1均有真实-v调用，实际搜索/执行路径无宿主混入。
完整Seed172项97,239,916字节、目标sysroot151项11,016,142字节；这是安装体积，
不是实际峰值内存或压力测量。最终app.elf 398920字节，SHA256
071469e5f42992f61711cebbc8df197a4d3416edbd33841515fa9745e2d1eb6a；
libgcc.elf 405040字节，SHA256
7f67aa5cdc016a8115848fae0b29f76afb657e423c47f8c74e139ff2a2b08402。

SDK v4：`.cache/xos_seed/sdk_snapshots/1ba7c52c568725cac63c4a9e603aabd61f30e00db430ca0e5afb4fcfee956490`，
manifest SHA256同目录名；完整文件哈希build/e08_sdk_v4_handoff.json。
与最终build/sdk全文件对比，只有manifest的build_id metadata不同，实际CRT/库/
user.ld/头及许可材料全部相同。旧SDK不就地改动。
派生Seed：`.cache/xos_seed/gcc/relinks/open_capacity_fix/seed_manifest.json`，SHA256
0a3c7f8ec85fea85219eaf86df2593df116fe740f9485cb4918a351dd35a66bb；
安装bundle manifest SHA256
95622b140f14da927b7463944cd7af79326324c7330e1725060c40e190bfcbee，
sysroot manifest SHA256
6b53a9233cae27369228771bea8b91a1b2a4d61805e361dae7eb29e7471360c6。
派生gcc SHA256 29a54a2a69de813ce153e55322a2a09d0fbd8d0a550120bb01c1db0f61b3e35c，
cc1 SHA256 85321572cf4aba927d7c95f0b7ef8008c04bd2798b04531a8f6396764825b12f。

最后一次构建后仅更新docs/交接说明，源码310项仍与manifest一致，git diff --check
通过。没有宣称完整make smoke/旧压力重跑、目标G++、collect2、-pipe或任意sysroot
重定位支持。当前没有剩余Luna编辑占用；下一位先读state和e08_gcc_seed.md，再按
reports/e08_cpp_abi_handoff.md接收实际target C++库/G++。不重跑本轮已完成测试，
后续压力继续由专人负责。
