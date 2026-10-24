# 主 agent prompt：主持 E08-4/5，运行基底、集成与验收

你在 /Users/xylo/Documents/XylophoneOS 工作，是本轮主负责人。另一 agent 是你的
工具链构建协作者，任务见 docs/prompts/e08_4_5_secondary.md；你负责范围划分、
接口与配置冻结、冲突裁决、集成和最终阶段结论。不要把对方交付当成已验收成果。
用户允许你使用 Luna 子代理提速；无需再确认一般实施选择。此 prompt 被执行后再
登记占用和派发任务；文档存在不表示另一 agent 已启动。

先按 AGENTS.md 阅读 Discipline.md → state.md → xos_plan.md，再读 decisions.md、
work_log/0013、0015、0017、e08_native_toolchain_plan.md、e08_pre1_design.md、
e08_runtime.md、e08_binutils_seed.md、licensing.md。修改内核/loader前另读
architecture_and_boot.md、cpp_subset.md、toolchain.md、e04_loader_sdk.md 和相关命令页。

目标：先完成 E08-4 的真实原生 C Seed，再完成 E08-5 的真实原生 C++ Seed；
E08-6 集成、E11 自举、Qt 移植不属于这两个阶段自动完成的内容。
后续压力测试有专人负责：不要重跑已经完成的压力轮次或扩展 soak；新增功能和
实际修复只跑对应验收/回归，保留版本绑定，不把旧测试结果迁移成新版本全绿。

## 你的责任与文件所有权

你独占 src/kernel/、src/shared/、src/user/、scripts/build.py、scripts/user_build.py、
Makefile、config/、共享文档及 licenses/ 的集成写入；不做无关重构。
另一 agent 独占 scripts/build_gcc.py、src/ports/gcc/、.cache/xos_seed/gcc/。
其发现的 libc/ABI/loader/权限缺项以实际调用点、错误和最小需求交给你，不跨界修。
你也不得直接修改其占用文件；通过交接文档约定变更后再转移所有权。

docs/e08_4_5_coordination.md 是协调入口，你维护任务/文件占用、接口版本、阻塞项、
SDK交付版本和验收状态；docs/state.md 由你统一汇总。协作者只写它的独立交接页。
这些路径是允许范围，不意味着必须全部修改；新增路径先写清责任。

## 实施顺序与并行工作

1. 在协调页登记本轮已启动的人员和文件范围。把协作者 prompt 交给用户启动；
   若用户已启动，直接以其交接页接收结果，不重复派发同一工作。
2. 先冻结最小交付合同：build/host/target、C/C++模式、目录布局、启动对象、
   SDK实际输入哈希、真实API支持、driver子进程树、target flags、内存上界。
   C Seed 的 cc1/driver 自身是 C++ 实现，必须先解决其 host 运行库依赖；
   这和“用户目标程序的 libstdc++ 已通过 E08-5”是两回事。
3. 与协作者并行落实有证据的运行时缺项：driver 的 pex/spawn/wait/临时文件/stdio、
   搜索路径、C++初始化与析构、必要 ABI；随后异常展开、RTTI、TLS机制。
   不根据头文件存在声称支持，不为了configure或链接填假成功stub。
4. 只有实际 GCC 进程树需要时才调整构造授权。当前 exec-driver 仅授权直接子任务，
   权限不向孙任务继承；collect2 等辅助工具可能再启动 ld，必须核实真实路径，
   选择最小适配或明确受限委托，不能全局授予普通程序构造权。
5. 你是 build/、最终SDK导出、QEMU验收盘和最终测试的唯一操作者。给协作者
   内容固定的SDK快照及manifest/链接输入哈希；它不能依赖正在变化的 build/sdk。
   ABI/runtime改变后发新快照，静态Seed必须重链接/构建并重新绑定，不能只换镜像。
6. E08-4先过gate，才把E08-5客体结果作为正式阶段验收。E08-5的源码研究、
   编译配置、依赖准备可以提前并行，不跳过C gate，也不重复构建同一套依赖。

## Luna 分工（由你实际启动并管理）

使用 Luna 模型，分别给明确文件范围；最多同时两名，连同你不超过当前可用槽位。
先核实是否已有相同任务存活，避免重复启动。派发时提供所需上下文和上述约束。

- luna_runtime：先分析真实缺项；你交付具体失败调用后，负责指定的用户态libc/
  SDK实现与小型探针。默认不动内核、loader、GNU构建文件、共享文档和build/；
  TLS若需要内核机制由你负责。不能提前造一整套POSIX。
- luna_cases：独占 tests/gcc_seed_smoke.py、tests/cpp_seed_smoke.py、
  tests/fixtures/gcc/、tests/fixtures/cpp/，编写下方功能验收及报告绑定，
  不修改旧压力测试，不自行运行共享build/QEMU；交付你串行执行。

子代理写各自独立交接页 docs/reports/e08_runtime_handoff.md、
docs/reports/e08_cases_handoff.md；共享状态由你收口。每次派发先在协调页登记；
无法独立划范围时由你自己实现，不为并行拆出互相覆盖的工作。

## Gate 与最终交付

E08-4：GCC driver、cc1、as、ld 均在XOS运行；单文件→多文件、头文件、-c/-o、
静态库及完整链接后客体执行；验证默认搜索路径不混入宿主输入，libgcc实际用例，
语法/链接/缺失文件错误非零且诊断可见，输入源码保留、对应任务/文件/页资源回收。
先采用临时文件顺序调用，-pipe不是第一gate前置；不把短消息pipe等同任意流水线。

E08-5：真实G++/cc1plus；单/多文件、头文件、静态库；基础容器/std::string、
跨翻译单元初始化/析构、异常抛出捕获与栈展开析构、RTTI、TLS分别有实际用例。
TLS验证初始化、任务间隔离和生命周期；无线程不声称验证过线程并发TLS。
当前接受基线是异常/RTTI/TLS必须，iostream可选；若仅子集跑通，标部分完成，
不得自行降级基线。内核受限C++子集不限制这些用户态设施。

功能gate记录实际内存/文件/任务使用与已知上限即可，不自行扩成压力测试项目。
任何不能满足的资源/功能应记录失败、根因与下一步，不用更换古老GCC或TinyCC绕过。

完成后更新state、相关设计/决定与work_log：实际命令、版本、SDK/Seed/系统/产物
哈希、执行/失败/未运行、许可证缺项和下一步。O11等只按真实证据局部更新；
E08-4/5完成不宣称E08整体完成。保留0017现场和旧历史报告。
localpilot不扫描/改动；不动日常工作盘，不清理他人改动；新自研Apache-2.0，
第三方保留原许可；不读取凭据，不自动提交/推送。
