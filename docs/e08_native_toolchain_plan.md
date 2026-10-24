# E08 分阶段计划：原生 GCC/G++

状态：**E08-0 审计、E08-pre1 设计均完成；E08-1 受限实现完成（见 0012）**。审计见
`e08_stage0_audit.md`，pre1 基线见 `e08_pre1_design.md` 与
`config/e08_pre1_baseline.json`。E06 的 newlib、E07 的 FAT16 工作盘、E04 的
用户态 ELF 装载是输入，但还不足以直接搬 GCC。以下阶段各有停点；未过 gate
不进入下一阶段，不用“能链接”代替“能在 XOS 内编译并执行”。

## 为什么必须拆

- 当前子程序只有 0/1/2 控制台句柄；libc 的 `open/stat/unlink` 返回 ENOSYS，
  文件服务没有 per-process 会话。编译器无法按路径读写源码/对象/临时文件。
- 工作盘 16 MiB、FAT16；文件服务 4 文件 × 24 KiB、RAM staging；用户进程
  64 页/任务、8 任务。原生 GCC 工具链的二进制、头文件、库和临时对象都放不下。
- 没有 `fork`/`exec`/`waitpid`/管道/环境变量等驱动编译器子进程的完整语义。
- 没有 libstdc++、C++ 异常/RTTI/TLS；G++ 不是只换一个前端。
- 宿主 `x86_64-elf-gcc` 是 macOS 可执行文件，只生成 ELF；它不是能在 XOS 内
  运行的 Seed。需要 Canadian cross（build/host/target 分开）或等价路径。
- 当前 ELF 上限 128 KiB、`exec-file` 一次读入缓冲；GCC 组件远大于此。

## 阶段与停点

| 阶段 | 内容 | 依赖 | 完成证据 | 规模 |
|---|---|---|---|---|
| E08-0 | 冻结版本/范围：GCC、Binutils、newlib/sysroot、C/C++ 设施、磁盘/内存上限、fork 或 spawn 策略 | E06 | 依赖矩阵、实际二进制尺寸、否决项清单（**已完成**） | S |
| E08-pre1 | 资源/接口设计：盘、RAM、页上限、文件会话、流式装载、spawn、C++ 范围 | E08-0 | 基线冻结：`e08_pre1_design.md`、`config/e08_pre1_baseline.json`（**已完成**） | S |
| E08-1 | 存储与文件 ABI：更大工作盘（先测后定 FAT16/32）、流式替换、>128 KiB 文件、宿主安装工具、per-process 文件会话/路径接口 | E07,E06 | 宿主放一个 >128 KiB 文件，XOS 读/写/同步/重启保留；无 RAM 全量 staging | L |
| E08-2 | 进程与 libc 基底：argv/env、spawn/wait、stdio 重定向/管道（按需 fork）、POSIX 文件/临时文件/errno、退出与资源回收 | E08-1 | 一个小程序按路径读源、写对象、启动子进程并收集状态 | L |
| E08-3 | 原生 binutils：`as`、`ld`、`ar`、`ranlib`、`strip` 的 XOS 可执行 Seed | E08-1,E08-2 | 在 XOS 内汇编、链接、静态库、strip；错误非零且诊断可见 | L |
| E08-4 | 原生 C Seed GCC：driver、`cc1`、libgcc、sysroot/搜索路径、启动对象 | E08-3 | XOS 内单文件→多文件 C、静态库、`-c`/`-o`/错误诊断；产物由 XOS 执行 | XL |
| E08-5 | 原生 C++ Seed G++：libstdc++、异常/RTTI/TLS 的取舍、C++ ABI | E08-4 | XOS 内 C++ 单/多文件、静态库、所选设施；缺失项明确记录 | XL |
| E08-6 | 集成验收：真实多文件 C/C++ 项目、编辑—保存—编译—运行、重启后产物仍在、资源回收 | E08-4,E08-5 | E08 验收日志与可复现命令；O11/O12/O13 局部证据 | M |
| （E11） | 原生重建 GCC/G++/自举比较 | E08-6 | 不属于 E08；另行记录 | XL |

## 每个阶段的停点

### E08-0：先做审计，不写“假接口”

- 固定 GCC/Binutils 源码版本、configure 参数、newlib/sysroot 和实际哈希。
- 实际测量 `cc1`、`cc1plus`、`as`、`ld`、libstdc++ 与测试项目的体积；
  再决定工作盘大小、文件上限、内存上限，不能先假定 16 MiB 够。
- 审计真实调用点：文件、目录、临时文件、进程启动/等待、环境、错误。
- 产出“必须实现 / 可裁剪 / 明确不支持”三张清单。没有清单不进入 E08-1。

### E08-1：文件和盘先够用

- 文件服务从“固定 4×24 KiB + RAM staging”升级为磁盘流式提交；保留原子替换
  语义，失败不截断旧文件。
- 增加工作盘的创建/扩容/格式策略；测试盘仍是临时副本，日常盘不当代价。
- 宿主安装工具：把 ELF/源码/头文件写入工作盘；普通构建不碰日常盘。
- per-process 文件会话与路径接口：每个任务有自己的句柄/游标，不能共享
  supervisor 的响应端点。先做单编译器客户端，不引入 VFS 全家桶。
- Gate：一个大于当前 128 KiB 上限的 ELF 能从盘上读取、校验、装载并运行；
  源码文件可读写、同步、重启保留。

### E08-2：编译器需要的进程/IO 语义

- 先支持“driver 启动一个子工具并等待”的最小路径：argv、环境、stdin/out/err、
  退出码；若 GCC 实际路径需要 `fork`/pipe，再按调用点补，不先造完整 POSIX。
- libc 的 `open/read/write/lseek/close/stat/unlink/rename` 接到 XOS 文件服务；
  临时文件、目录和错误码按实际工具需求实现。
- 资源上界：子进程、打开文件、临时文件、内存；失败要返回错误并回收。
- Gate：一个真实小程序按路径读取源码、写对象、启动子工具、收集状态；
  失败路径不破坏已保存源码。

### E08-3：先搬 binutils

- 先让 `as`/`ld` 在 XOS 内运行和产出正确目标文件；`ar`/`ranlib`/`strip`
  随后。它们比 GCC 小，能先验证文件、进程和链接器路径。
- E08-3 gate 已通过；本阶段压力测试计划见 `e08_3_stress_plan.md`，实际结果见压力报告及0017修复追记；
  后续压力由专人负责，不在本轮重复。
- 保持宿主交叉工具只用于生成 Seed，不在宿主代执行 XOS 程序。
- Gate：XOS 内汇编、链接、静态库、strip 的实际产物能在 XOS 执行。

### E08-4/E08-5：C Seed，再 C++ Seed

执行分工见[e08_4_5_coordination.md](e08_4_5_coordination.md)及其中两份prompt。
主agent负责运行基底/ABI/集成/最终gate，另一agent负责统一GCC构建闭包；
Luna在主agent管理下承担边界明确的子任务。配置准备可并行，正式C/C++ gate按序。
E08-5异常/RTTI/TLS沿pre1已定基线执行；子集成功不能替代完整阶段结论。

- C Seed 先单文件、再 `-c`/多文件/静态库/错误诊断；搜索路径不得混入宿主库。
- C++ 单独决策：是否必须异常/RTTI/TLS/libstdc++；缺什么就明确记录，不能
  把“C 能编”写成“G++ 可用”。
- Gate：XOS 内编译出的多文件 C/C++ 程序由 XOS 执行；错误编译非零且不破坏源码。

### E08-6：集成验收

- 真实项目：至少一个多文件 C、一个 C++（含头文件/静态库），编辑—保存—
  `sync`—编译—运行；重启后再运行产物。
- 记录资源回收、失败诊断、磁盘/内存峰值；旧 E01–E07 回归保持。
- 只有 E08-6 通过才称 E08 完成；E11 自举不是 E08 前置。

## 明确不做/不假设

- 不先做完整 POSIX、Linux 兼容层、VFS 全家桶或动态链接。
- 不把 TinyCC/自写小编译器当作 GCC/G++ 验收；可以作为可选工具另行记录。
- 不为了消除链接错误写“永远成功”的 `open`/`fork`/`mmap`。
- 不把宿主 `x86_64-elf-gcc` 或 macOS 二进制直接当 XOS Seed。
- 不把 16 MiB/24 KiB 文件上限当成能容纳工具链的证明。
- 不在一轮内同时改内核、文件、libc、binutils、GCC、C++。

## 当前停点

E08-1、E08-2、E08-3受限gate已通过，完整限制和证据见state.md、
e08_storage_and_sessions.md、e08_runtime.md、e08_binutils_seed.md与0012/0013/0015。
下一开发阶段E08-4：GCC C Seed的driver/cc1/libgcc/sysroot真实闭包与多文件编译。
Qt主线与SDL次选已纳入xos_plan.md的E13–E20；本次仅扩展计划，不改变E08-4顺序。GCC/G++尚未实现，O11–O13
不整体标通过；资源基线仍需测真实GCC/Qt峰值，不由小汇编链路替代。

0020更新：E08-4受限C功能gate已通过（82ffcecab8ccbcce，4组/15命令）；上文早期
“下一阶段E08-4/GCC尚未实现”为历史。当前下一阶段E08-5真实G++与target运行库，
E08-6、O11–O13和E08整体均未据此标通过，压力测试由专人负责。

0022最新结论：E08-5原生G++4组/14命令通过，E08-6 C/C++编辑/正常重启两个增量
均通过，E08受限功能范围收口，O11/O12/O13按该静态配置通过。当前状态和版本
绑定见reports/e08_acceptance.md；上文早期停点为历史，不冒称真实高水位、完整旧
回归、压力、完整POSIX/标准库或自举。后续压力仍由专人负责。
