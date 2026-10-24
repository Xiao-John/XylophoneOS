# 0021：E08-5开工与E08-6提前准备

2026-10-24。用户要求启动E08-5，分配从端，争取当晚进入E08验收。
进度目标不降低异常/RTTI/TLS基线，不将单语言部分验收称为E08完成。

## 已启动与分工

主端负责运行时/SDK/安装整合和正式客体gate，build/只由主端串行构建/运行。
Luna runtime负责TLS析构/正常exit适配及独立探针；Luna cases负责新E08-6 harness和
C/C++ fixtures，已交付冻结。准确文件范围见state.md和协调页0021。
外部从端任务已写docs/prompts/e08_5_secondary.md，待用户转交/启动；没有可靠证据
时不能记为从端正在构建。其GNU源码/脚本/新私有cache与主端互不覆盖。
优先A批target库（先解锁交叉ABI），B批G++/cc1plus，最后合并正式原生gate。

## 主端当前变更

- prepare_gcc_seed.py可选G++/target运行库manifest/prefix，沿用明确根/白名单，
  不从宿主找标准库；cpp_seed_bundle.py绑定target角色、实际库/头/SDK哈希、
  异常RTTI开启、六项设施声明与local-exec静态profile；直接GNU ld，collect2不启用。
- C++头使用-isystem，C头使用-idirafter，正确支持#include_next。真实同版本宿主
  G++ -###曾暴露%1也适用cc1plus，初版C -isystem先于C++目录；已据实际展开修正。
  -###只解析/展示命令，没有执行子工具、编译或客体代码，不是C++验收。
- 共享read_manifest可显式指定必需工具，G++ gate不强要求独立cc1；C默认保持原合同。
- 正式native C++ fixture增加从archive跨TU抛出、跨帧两个RAII析构、局部static只构造
  一次、非平凡TLS析构先于global析构；仍待实际目标运行库和G++验证。
- Luna新E08-6 runner支持C/C++增量，每种都包含实际edit保存/改源码、multi-TU
  archive编译运行、sync/正常同盘重启、离线源与工具哈希比对；单语言只算部分通过。

## 已运行与进行中

- cpp_seed_bundle_cases.py 5个合同用例通过，包含host闭包拒绝、exception/RTTI关闭
  拒绝、输入hash变化/不完整设施/缺libgcc拒绝；不是客体测试。
- 改动后C bundle真实白名单readonly预检通过：172 Seed、151 sysroot、10工具、
  108256058字节、0诊断；没有重复已完成的E08-4功能gate。
- 新E08-6 C实际编辑/编译/重启通过4项、18命令，passed_partial_language；
  系统82ffcecab8ccbcce、镜像SHA256
  bd5dd6d7342b42ce5904f0937675c3285f9058fa93d0568792b63e3d31530a8d。
  客体edit :c/:wq真实保存main，V1→重新编译V2输出变化；sync正常同盘重启执行V2，
  源码逐字节持久化、10个工具离线hash不变。V2 app.elf为612336字节，SHA256
  a3c057cda3d375e134fdd4af72bb40ec224a2e8d628f7fa4b6c5e4035f9dac61。
  报告build/e08_6_c_report.json、日志build/e08_6_c_integration.log；保留测试系统
  build/e08_6_c_82ffceca.img及e08_6_c_system_manifest.json，避免新构建覆盖证据。
  只是C语言部分，不因提前验证就越过E08-5将E08整体标完成。
- C++ target库尚未交付，正式E08-5仍not_run；E08整体未完成。不跑历史压力/soak。

新自研代码Apache-2.0；已有GNU依赖版本不变。原SDK v4/已验收C Seed不就地修改；
TLS出口变化会发布SDK v5，前端/库对象可继续构建，最终链接再换快照。
localpilot/日常盘不触碰，不提交/推送/读取凭据。失败照常落盘，不靠省略设施赶时间。

## 本轮主端交付完成

实际新增非平凡thread_local对象未定义符号确认是__cxa_thread_atexit。XOS实现单进程
单用户线程私有LIFO链；注册malloc失败/空callback返回非零。强exit使main返回和
显式exit统一：先TLS析构，再newlib __call_exitprocs/stdio handler，最后_exit。
TLS析构中新注册先pop/free再调用；普通handler中新注册TLS会再次处理。递归exit
直接_exit，kill/_exit不承诺正常析构，无DSO卸载/线程语义。未复制GNU源码进自研文件，
依据实际匹配版本出口顺序；链接确认真实newlib归档符号可用，无重复定义。

主端scripts/user_build.py接入独立磁盘tls_exit_probe，不增加bootstrap模块大小。
make build通过，最终f40c9a254b5433d7，源码SHA256
f40c9a254b5433d7359428563d7404d3dad2f1d7cbb01c0ccdc0c3805479745c；
xos.img SHA256 b2b2d11621848b69b7ef46a88ee00390d91f3a2c07b77db89e5138d7546cc87f。
python3 tests/tls_exit_smoke.py真实客体两路径通过，所有marker恰好一次、严格顺序，
逐路径资源[130342,2,0]复原；probe SHA256
87abf287be1c9cd41c85afd13c7e3b2095d6a5af14035624fe60cf1e109cbac0。
日志build/e08_5_runtime_build.log、e08_5_tls_exit.log，报告tls_exit_smoke_report.json。
python3 scripts/license_audit.py通过7份材料/已登记组件hash；324项当前源码与系统
manifest一致，Python语法编译及git diff --check通过。未重跑旧CRT/C gate/压力轮次。

SDK v5：.cache/xos_seed/sdk_snapshots/3a302b5cd7e1cdab0f594b0d16d7ca92b753fec7b2efcc6347b01e5a69542edd，manifest SHA256同目录名；
完整文件hash build/e08_sdk_v5_handoff.json；libxos.a SHA256
2e4a4c7c0107c2ead1960ffbcf56565ff0548bfd6da1aeb674b9796c6dea340c。
所有旧快照保留不变，v5只增加用户运行库退出语义，无内核消息/系统调用ABI变更。
prepare_gcc_seed.py的--target-sdk允许工具自身旧SDK与应用目标SDK分别绑定；
原始工具manifest/input_manifests与tool_runtime_sdks保留其真实构建来源，不重标旧工具。
实际C工具+v5应用sysroot readonly预检通过：172/151项、10工具、0诊断，
报告build/e08_5_v5_preflight_report.json；不是重跑C客体功能gate。

新增5个C++合同用例通过；正式C++fixtures用真实host闭包头做-fsyntax-only通过，
仅语法检查，不链接该闭包、不据此标target exception/RTTI/标准库通过。G++ -###只
核对specs展开，实际-v命令确认C头应放%1的-idirafter，C++目录放%2的-isystem。

## 接续顺序

本轮主端准备/运行缺项与C增量已完成，Luna均已冻结；外部从端未确认启动，需转交
prompts/e08_5_secondary.md。主端继续持有共享状态/SDK/build，无其他编辑占用。
从端A批目标库一到：以v5和reports/e08_cpp_abi_handoff.md合同跑独立ABI探针；B批
G++/cc1plus一到：prepare_gcc_seed.py带--gxx-manifest/--runtime-manifest/
--runtime-prefix/--target-sdk生成CPP bundle，再跑cpp_seed_smoke.py。不要装host闭包。
随后只跑e08_integration_smoke.py --language cpp的新C++编辑/重启增量；综合各阶段
真实证据决定E08-6/整体结论。C部分已通过不重复跑，压力仍由专人负责。
E08-5正式gate仍not_run，目标库/原生G++尚未交付；E08整体没有完成。
