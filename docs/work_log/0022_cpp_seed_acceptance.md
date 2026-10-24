# 0022：接收E08-5，从ABI进入原生C++验收

2026-10-24。用户交付reports/e08_5_secondary_handoff.md，主端接管集成/QEMU，
不审计或重跑从端完整构建，不重跑C gate/C编辑重启/历史压力。没有其他活跃代理。
原从端源码、已编对象、SDK/库/安装manifest保留，修复放独立派生目录。

## 接收与当前证据

从端A/B原manifest为src/ports/gcc/e08_5_target_runtime_manifest.json、
e08_5_gxx_manifest.json；目标库编译输入SDK v4，工具host闭包仍无异常/RTTI，
目标库开启异常/RTTI/local-exec，两类不混用。应用链接显式采用已验收SDK v5。
正文libsupc++哈希沿用了旧host哈希，但实际文件匹配B manifest的目标库哈希
b8564d4be171caef04c84f20905fd5936d6547d8d786f3cc3113af1a79a675b2；
采用实际文件+B绑定，不把正文旧值当目标库，原A manifest缺失supc++项/role由主端
显式接收规范化，保留原始manifest与构建SDK来源。

第一次ABI构建遇到真实重复__cxa_thread_atexit：旧SDK v4配置出的GNU
atexit_thread.o仍定义atexit回退，而v5已提供正确TLS生命周期入口。
scripts/derive_cpp_runtime.py以新独立目录复制明确include与三个归档，设置GNU
既有配置宏
_GLIBCXX_HAVE___CXA_THREAD_ATEXIT=1，并移除两个C++归档内各一个atexit_thread.o。
实际GNU源码atexit_thread.cc在该配置下实现体为空，系统libc负责入口；不留重复
定义或让旧atexit回退覆盖v5顺序。ar重新建索引，保存输入/输出hash、命令和配置改动；
保留上游头内GNU条款/运行库例外，不替换为Apache。

六项独立ABI已在真实XOS通过：string/vector、异常跨帧RAII展开、RTTI、local static、
非平凡TLS析构、跨TU构造/逆序析构。报告build/e08_5_abi_v5/cpp_abi_smoke_report.json，
同目录builder报告、build/e08_5_abi_v5.log及cpp_abi_smoke_serial.log。
系统f40c9a254b5433d7（SDK实际文件与v5一致），不是原生编译器gate。
第一版TLS重复定义失败保留build/e08_5_tls_duplicate_failure.json。

最初适配manifest在build/e08_5_runtime_v5_manifest.json；随后脚本已能直接接收
原始A/B，正式派生为.cache/xos_seed/gcc/relinks/target_runtime_v5_receipt/。
比较前后include_dirs与archives的所有实际hash完全相同，仅接收来源metadata更完整，
故不重跑ABI。原始工具/库与旧SDK均未覆盖。

## 原生G++首次失败与修复

原始g++ --version在_free_r触发#GP，RIP0x40112f89；反汇编lrealpath只ret。
这是E08-4已暴露的同一真实根因，从端B没有纳入0007回退。
保存build/e08_5_gxx_first_launch_failure.json。scripts/relink_gcc_seed.py增加--gxx，
读取从端真实build3.log两条最终链接命令，仅编译修复的lrealpath.o并重链接
xg++/cc1plus，独立输出.cache/xos_seed/gcc/relinks/gxx_lrealpath_v5/。
绑定原始对象/归档/host库/SDK/编译器/补丁与输出hash；不完整configure/all-gcc重编。
仅安装修复g++/cc1plus，C工具继续用0020已验收派生；collect2不纳入验收，仍直接GNU ld。

当前build/cpp_bundle组合174个Seed、1036个sysroot项，12工具，185903068字节，
readonly预检0诊断。新统一系统构建/正式原生G++验收进行中，结果在下节补充。

## 最终通过与本组收口

E08-5原生G++ gate在6b7d5cfc3612fdf4通过4组/14命令：string/vector、局部静态、
跨TU全局构造/析构、非平凡TLS先于global析构、从静态archive跨帧抛出/两个RAII
析构、RTTI；PID35/36两任务初始化TLS并存/yield隔离、wait回收；语法/链接错误
非零，源码全部逐字节不变，每条命令资源恢复[130342,2,0]。
产物cpp_app.elf 848056字节，SHA256
445724fd060d30da740ce072a35baa4a1497cf6bbc3c0773ff52967b8ee72db0。
报告build/cpp_seed_smoke_report.json、cpp_seed_smoke_serial.log、e08_5_native_cpp_fixed.log；
保存当时build/e08_5_native_6b7d5cfc.img和e08_5_native_system_manifest.json。

随后仅更新licenses/components.json的目标库用途登记，make build得到最终
2c3876e640840ff5，源码SHA256
2c3876e640840ff556a0aa80e5dfdce000e944c6649839ff41092ca833242e18，
xos.img SHA256 1c2cfa90d65b9a9585ac3d5cef32c8376b1806e65f7502321912b2e15b54454c。
对比native gate清单，唯一源码变更是许可组件表；实际CRT/库/头与SDK v5全部相同，
只SDK manifest metadata/组件声明不同，不重跑无代码变化的native设施测试。

最终系统下运行：

```sh
python3 tests/e08_integration_smoke.py --language cpp   --cpp-seed-manifest build/cpp_bundle/seed_manifest.json --cpp-seed-root .   --cpp-sysroot-manifest build/cpp_bundle/sysroot_manifest.json --cpp-sysroot-root .   --run-guest --report build/e08_6_cpp_report.json
python3 scripts/license_audit.py
```

C++编辑/重新编译/运行/同步重启4项、18命令通过，status=passed_partial_language。
真实编辑main后输出V1→V2，正常重启仍V2，源码和12个工具hash全部正确。最终C++
app.elf 791368字节，SHA256
22623589bad346e7498980d29ef86a02d0d81821134d2befb6aa82acb7661970。
报告build/e08_6_cpp_report.json，日志e08_6_cpp_integration.log及e08_6_boot1_serial.log/
e08_6_reboot_serial.log；此轮没有重跑0012–0021已完成的C/CRT或压力轮次。

主端合并此前C编辑持久化报告，判定E08-6受限功能gate通过，E08当前功能范围收口。
单语言原报告仍保留partial，不改标；综合结论docs/reports/e08_acceptance.md、
build/e08_acceptance_report.json绑定所有报告及版本。O11/O12/O13在当前静态配置
通过；不扩大为完整POSIX/标准库、自举、最终镜像全量旧回归或压力全绿。
原生观察最大单次子任务退出回收20501页不是内存高水位；安装185903068字节不是
磁盘峰值，真实峰值/soak仍未测，后续压力继续专人负责，不为此新增压力项目。

## 最终输入指纹与接续

原A manifest SHA256 538baa523869bda07455c79c0d406a69bfbc8442469d96a5b28e2741df9c689e；
原B manifest SHA256 ddc22e04954c68d871d4ed70adb7c224de2d8bf2d1213aa4e3a49b5433964e88。
派生G++ manifest .cache/xos_seed/gcc/relinks/gxx_lrealpath_v5/seed_manifest.json，SHA256
29946d9fc850d04d7a95f0e03d2cf934225b9a887007f74387c76ebd05d6e77d。
派生目标库 .cache/xos_seed/gcc/relinks/target_runtime_v5_receipt/manifest.json，SHA256
fe685d9f20fe7594440fb4a5c3adb77ae640ce68bec2403aff772b721ba09988。
组合build/cpp_bundle/seed_manifest.json SHA256
327e2cb0f548dfb721b9ca968c2d3ec84f01e7633b0b3e9d5207bf3c7b5ea448，
sysroot_manifest.json SHA256 e3fd2aaa4b8a0c272406aa3091225cdef058ce2a4aa0280b371c1a311344aee7。
SDK v5 manifest 3a302b5cd7e1cdab0f594b0d16d7ca92b753fec7b2efcc6347b01e5a69542edd保持冻结。

327项当前源码与最终manifest核对一致，新增/修改脚本py_compile及git diff --check
通过；7份SDK许可材料与登记组件hash核对通过。逐成员许可/公开源码发布核对尚未
完成，不以材料检查替代法律认证。未提交/推送/读取凭据，localpilot/日常盘未动。
所有临时QEMU已关闭，没有剩余代理编辑占用；主端本组结束。下一组先读state、
e08_cpp_seed.md、综合验收报告，再由用户安排E09交付/试用或后续已计划支线。
