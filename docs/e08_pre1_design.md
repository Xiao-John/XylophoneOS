# E08-pre1 设计：原生工具链的资源与接口包络

状态：**E08-pre1 完成（设计/基线冻结）；E08-1 未开始**。输入是 E08-0 审计。
目标不是马上写 GCC，而是先回答“在哪个内存/磁盘/进程/文件模型下，原生 Seed
才有意义”。决定记录见第 12 节与 `config/e08_pre1_baseline.json`。

## 1. 设计目标与非目标

目标：

- 给出一个能容纳 GCC/Binutils Seed 的**资源包络**（RAM、工作盘、进程/文件上限）。
- 定义**文件服务 v2**：路径、目录、按进程会话、流式大文件；不再用 24 KiB
  RAM staging 假装能装工具链。
- 定义**大 ELF 装载**：从工作盘按段读取，不能要求 supervisor 先放一个 40 MiB
  缓冲，也不能假定 64 页/256 KiB。
- 定义**进程基底**：编译器 driver 启动 `cc1`/`as`/`ld` 所需的最小
  spawn/wait/stdio/管道；不先造完整 POSIX。
- 定义 **Seed 构建路径**：Canadian cross、C 先行、C++ 单独决策。
- 给出可验收 gate；未过 gate 不进入 E08-1。

非目标：完整 POSIX、VFS 全家桶、动态链接、Linux 兼容、E11 自举；不在 pre1
改内核/文件服务代码。

## 2. 审计事实（决定设计的下限）

- `cc1` 约 40 MiB、`cc1plus` 约 43 MiB，宿主是 arm64 Mach-O；不是能在
  x86_64 XOS 运行的 Seed。
- GCC 安装树约 192 MiB；GCC 源码包 107 MiB、Binutils 源码包 29 MiB。
- 当前工作盘 16 MiB、文件 4×24 KiB、进程 64 页（256 KiB）、8 任务、64 MiB
  QEMU RAM。
- `libstdc++.a`/`libgcc_eh.a` 不存在；子程序没有路径文件 I/O，没有
  fork/exec/waitpid/pipe/环境变量。
- 结论：**资源下限必须整体提高**；只改文件上限或只把 cc1 塞进 boot 镜像都不行。

## 3. 候选资源包络（建议值，待批准）

| 项目 | 当前 | 候选 | 理由 |
|---|---|---|---|
| QEMU RAM | 64 MiB | **512 MiB** | 单 cc1 约 40 MiB，加上页表、堆、磁盘缓冲和工具链余量；64/128 MiB 都会把“能启动”误当“能编译” |
| 内核物理页上限 | 128 MiB | **512 MiB** | 需要重新审计内核 identity map、页分配和 QEMU 内存窗口；不是只改 `-m` |
| 用户地址空间 | 1 GiB 窗口 | 保持 1 GiB | 足够容纳 40 MiB 文本 + 堆；不引入 64 位大地址复杂化 |
| 用户页上限 | 64 页 | **65536 页（256 MiB）** | 预载/工具运行需要；必须配页表与回收压力测试 |
| 任务数 | 8 | 先保持 8 | driver + cc1 + as + ld 可顺序运行；并发工具不是 Seed 必需 |
| 工作盘 | 16 MiB FAT16 | **2 GiB FAT32** | GCC/Binutils 源码、sysroot、对象/临时文件、Seed 与测试；独立盘，不当 build/ |
| 文件上限 | 24 KiB | **磁盘剩余空间** | 流式提交；协议单块仍 4 KiB；不再有 24 KiB 语义 |
| 文件命名/路径 | 8.3 平铺 | **FAT32 + LFN + 目录** | `#include <sys/...>`、sysroot、源码目录必须真实路径；不是把所有头文件改名塞平铺 |
| ELF 上限 | 128 KiB | **磁盘/内存允许的 Seed 大小** | 由流式段装载和页上限约束，不再有固定 128 KiB |

这些是 **E08-pre1 冻结基线**，写入 `config/e08_pre1_baseline.json`；不是当前
已实现值。尤其 RAM 与盘容量仍需在 E08-1 先测 QEMU/ATA 吞吐与页表压力，若实测
不成立，必须改基线并记录，而不是偷偷回退。

## 4. 文件服务 v2（核心设计）

### 4.1 数据面

- 工作盘 FAT32，保留目录/LFN；客户端使用绝对/相对路径（先支持绝对根路径）。
- 文件按**流式 open/read/write/lseek/close**，单次消息 4 KiB；大文件不经过
  supervisor 的全量缓冲。
- 保存仍是“写临时文件 → 同步 → 原子替换/恢复”，但 staging 在磁盘临时文件，
  不在 RAM；失败不截断旧文件。编辑器仍可用 8 KiB 缓冲，但文件服务不限制
- 目录操作：`opendir/readdir`、`mkdir`、`unlink`、`rename`；不提供完整 VFS
  挂载、符号链接或权限模型。

### 4.2 会话与端点

当前只有 supervisor 拥有 files 的请求/响应端点；子程序只有 0/1/2 控制台。
候选方案：

- **A. per-task 文件会话（推荐）**：spawn 时为需要文件的子任务分配
  request/response 端点；files 服务按会话保存 handle 表。请求带会话 token；
  kernel 校验发送权，files 不依赖客户端自报身份。
- **B. supervisor broker**：子任务只连 supervisor，supervisor 转发 files。
  实现较慢但少改端点；会成为单点/额外拷贝，不利于编译器大量 I/O。
- **C. 内核文件 syscall**：内核转发 files 协议。能让 libc 简单，但把文件协议
  塞回内核，违背职责分离，暂不选。

E08-pre1 推荐 A；pre1 只定义接口，E08-1 再实现。会话身份必须由 kernel 或
端点记录提供，不能重复 E05 的“客户端自报 owner”当成安全边界。

### 4.3 libc 接口

`open/read/write/lseek/close/stat/unlink/rename/mkdir/opendir/readdir` 接到
文件服务；`fopen`/stdio 在其上实现。临时文件使用工作盘目录；错误用 errno
映射，未支持的操作继续返回 ENOSYS，不写假成功。

## 5. 大 ELF 装载（不能全量塞 supervisor）

当前 `spawn`/`exec-file` 把完整文件读入 128 KiB 缓冲；GCC 二进制不可能。
候选：

- **流式段装载（推荐）**：打开文件并保持打开，读 ELF header/PHDR，按 LOAD
  段分块读入目标物理页；打开期间 files 拒绝替换，校验/执行使用同一文件版本。
  不要求整个 ELF 在 supervisor 内存中。
- **文件 backed 按需分页**：更省物理内存，但需要页故障处理、文件句柄生命周期
  和回收；首轮 Seed 不必先做。
- **整文件预读**：最简单，但要 40 MiB 级缓冲/物理页，和现有 128 KiB 机制不兼容。

E08-pre1 推荐**流式段装载**；先不做 demand paging。用户页上限提高后，装载
40 MiB cc1 仍需要容量决定；失败必须回滚，不能留半成品任务。

## 6. 进程基底

GCC driver 要启动 `cc1`、`as`、`ld`，并处理 stdout/stderr、退出码、临时文件。
候选：

- **posix_spawn + waitpid + pipe（推荐）**：按实际 driver 调用点实现；不先做
  完整 fork/信号/作业控制。
- **fork + exec**：兼容性更广，但复制地址空间/文件表/信号语义成本高；只有
  审计证明 GCC driver 必须 fork 时才升级。
- 环境变量、cwd、fd 重定向按工具需要加入；argv 上限从 8 提高，路径长度从
  63 提高；这些是协议/ABI 设计，不能靠截断。

E08-1/2 要审 GCC `pex`/driver 的调用点，再决定是否支持 `posix_spawn` 配置；
不先实现“看起来像 POSIX”的空壳。基线是先用 posix_spawn + waitpid + pipe，
只有实际调用点证明不够时才加 fork/信号。

## 7. Seed 构建与 C++ 范围

### 7.1 分层顺序

1. 宿主交叉工具只生成 XOS 可执行的 **Canadian cross** 产物；不在宿主运行
   XOS 程序。
2. 先搬 `as`/`ld`/`ar`，验证文件/进程/链接路径。
3. C Seed GCC：`--enable-languages=c`、静态、无 bootstrap；sysroot 只含 XOS
   头/新 libc/库，不混宿主。
4. C++ Seed：`--enable-languages=c,c++` + libstdc++；异常/RTTI/TLS 单列决策。
5. E11 才谈自举；不是 E08 前置。

### 7.2 C++ 最小范围（基线）

| 设施 | E08-5 基线 |
|---|---|
| C++ 前端 `cc1plus` | 必须 |
| libstdc++ 基础容器/`std::string` | 必须 |
| 异常 | 必须（G++ 默认 ABI；禁用需重新决策） |
| RTTI | 必须（同上） |
| TLS | 必须（libstdc++/ABI 需要；失败则 E08-5 不通过） |
| iostream | 可选；不作为 C++ gate 的前置 |
| 完整 STL/线程/动态链接 | 不在 E08 Seed 范围 |

不能把“C 编译通过”写成“G++ 可用”；G++ gate 要单独过。若 E08-5 最终只能
提供 `-fno-exceptions -fno-rtti` 子集，必须把 E08-5 标为部分完成，不能写成
完整 G++。

## 8. 磁盘与宿主安装

- 工作盘 2 GiB FAT32，独立于 `build/`；`make disk` 显式创建/格式化，已有盘
  默认不动。
- 宿主安装工具把源码/sysroot/Seed 写入盘；测试用临时副本；`make smoke` 不写
  日常盘。
- Root 布局候选：`/sysroot/include`、`/sysroot/lib`、`/src`、`/tmp`、`/out`；
  8.3 限制不能用于 sysroot 路径，必须 LFN/目录。
- 磁盘吞吐先测 ATA PIO 8 扇区/请求下的实际 MB/s；200 MiB Seed 的装载/复制
  不能只按容量估算。

## 9. 停点与验收

E08-pre1 已完成：资源包络、文件会话/路径、流式装载、spawn 方向、C++ 最小范围
和 E08-1 gate 都已冻结。E08-1 仍然**未开始**；开始前要做一次 512 MiB/2 GiB
盘上的 ATA 吞吐和页表压力测量，若基线不成立则先改基线。

E08-1 的第一个 gate：**从盘上放 >128 KiB ELF，按路径读写文件，sync 后重启
保留**。后续 gate 仍按 `e08_native_toolchain_plan.md`。

## 10. 风险与明确不承诺

- 512 MiB RAM/2 GiB 盘会改变 QEMU/内核内存模型和测试时间，需重新验证旧回归。
- FAT32+LFN、per-task 会话、流式装载、spawn 都是大改动；不能在一个小补丁里
  同时完成。
- 40 MiB cc1 的文件 I/O 和页表压力可能要求 demand paging；若预载吞吐不可接受，
  预1 的推荐方案要回退到文件 backed 分页并重新评估。
- 不承诺完整 POSIX、完整 libstdc++、线程、动态链接、Linux 兼容或 E11 自举。
- 没做实现前，O11–O13 继续是 not_run。

## 11. 本轮状态

E08-pre1 完成：设计/基线已冻结，**未执行 E08-1**。下一步是 E08-1 的吞吐/
资源实测与存储/文件 ABI 实现；未过 gate 不进入 binutils/GCC。

## 12. 决定记录

| ID | 决定 |
|---|---|
| P1 | 512 MiB QEMU RAM、512 MiB 内核物理页上限、1 GiB 用户窗口、65536 用户页/任务、8 任务。 |
| P2 | 2 GiB FAT32 专用工作盘；LFN/目录；独立于 `build/`；测试临时副本。 |
| P3 | 文件服务 v2：per-task 文件会话（方案 A），路径/目录，流式 open/read/write/lseek/close，4 KiB 消息，磁盘 staging，磁盘剩余空间为文件上限。 |
| P4 | 大 ELF 用流式段装载；先不做 demand paging；打开期间 files 拒绝替换，失败回滚。 |
| P5 | 进程先做 posix_spawn + waitpid + pipe；fork/信号只在 GCC 实际调用点证明确需时加入。 |
| P6 | Seed 版本冻结 GCC 16.2.0、Binutils 2.47、newlib 4.6.0.20260123；Canadian cross；顺序 binutils → C GCC → C++ GCC。 |
| P7 | C++ 最小范围：前端、libstdc++ 基础容器/string、异常、RTTI、TLS；iostream 可选；线程/动态链接不在范围。 |
| P8 | E08-1 第一 gate：>128 KiB ELF 从盘上装载；按路径读写；sync 后重启保留。 |

这些是规划基线，不是已实现事实；代码/测试尚未改成这些值。若实测/实现推翻，
必须更新本表与 state，不得静默偏离。
