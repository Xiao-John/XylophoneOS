# XylophoneOS / XOS

给自己和朋友玩的独立操作系统。目标：x86-64 微内核，NASM + 受限 C++，
逐步实现系统内编辑、保存、GCC/G++ 编译和运行程序。

开发前读 [开发纪律](docs/Discipline.md)、[当前状态](docs/state.md) 和
[计划](docs/xos_plan.md)。`localpilot/` 是独立项目，不参与 XOS 构建。

## 公共多线程：E13-T 独立开发分支

本分支实现单核抢占的 1:1 内核线程：同进程共享地址空间与权限，独立栈/guard、
静态 TLS 与 FPU 上下文；支持线程创建事务、join/detach、退出仲裁、单调时间、
比较等待/唤醒，以及独立线程 SDK 的 pthread/newlib/C++ 运行库。
普通进程最多 4 线程，全局 8 进程/32 线程槽；新线程默认 256 KiB 栈。

普通应用使用单独生成的 `build/threading_sdk`；`build/sdk` 继续是单线程运行库，
不能仅复制 pthread 头混用旧库。真实客体验证、ABI/地址图、构建与使用命令、
失败日志及限制见 [线程实现与验收](docs/threading_implementation.md)。
SMP、完整 POSIX pthread、动态 TLS、取消、实时调度和 Python/Qt 接入另验。
本分支不更新 0.0.1 的发行标签、镜像附件或日常工作盘。

## 首个正式发行：0.0.1-1024

[XylophoneOS Revival version 0.0.1-1024](https://github.com/Xiao-John/XylophoneOS/releases/tag/v0.0.1-1024)
提供可直接启动的镜像、预装原生 GCC/G++ 的工作盘和独立 SDK。
下载 images 包，解压后运行 `python3 launch.py`，在 `xos64>` 输入 `run`。
详细操作、配置与限制见 [发行说明](docs/releases/0.0.1-1024.md)。
E08 受限 C/C++ 编辑、编译、运行、同步重启闭环已验收；压力测试仍在进行，
不声称压力矩阵或最终镜像全量旧回归全绿。

BIOS 启动后进入 x86-64 C++ 内核：E820 物理页管理、异常 panic、串口调试控制台、
ring3 用户任务、每任务地址空间、PIT 定时抢占、最小 IPC、用户故障隔离、
任务资源回收与用户态 `sup> ` 监督终端。启动后停在 `xos64> `；输入 `run` 进入
八个用户任务的演示，之后由 supervisor 接管串口，不再返回内核控制台。
supervisor 用最小 SDK 在用户态装载静态 ELF64、传递 argv/初始句柄并等待结果；
E05 增加独立 ring3 文件服务与 `ls/cat/stat/rm/edit/exec-file`，E07 把 RAM 后端
换成独立 FAT16 工作盘（ATA PIO + FatFs）、原子保存、`sync` 与重启恢复；
E06 接入 newlib 4.6，提供常用 C 库、SSE/x87 任务上下文和 `libc_hello`。
E08-1 增加 512 MiB 内存基线、2 GiB FAT32 新盘、ASCII LFN/目录、per-task 文件会话、
磁盘流式保存及大 ELF 按段装载；原 FAT16 盘保持兼容。
E08-2 接入真实文件stdio、动态堆、受限posix_spawn/waitpid与pipe；E08-3已运行真正
XOS-hosted GNU as/ld/ar/ranlib/strip，客体生成和strip的ELF均可执行、同步重启保留。
上述为历史阶段证据。E08-4/5 已加入原生 GCC/G++，E08-6 完成受限 C/C++ 闭环，
分构建证据见 [E08 总览](docs/e08.md)。当前没有完整 shell。

```sh
make disk       # 显式创建/格式化 work_disk.img（已有盘默认不动）
make license-audit # 检查许可登记与 SDK 声明副本
make libc-audit # 从实际 newlib 产物生成依赖清单 build/libc_audit.json
make build      # 主线镜像、kernel.elf、练习镜像、符号与哈希清单
make run        # 64 位内核 + 串口调试控制台；需要已有 work_disk.img
make run_vga    # macOS：显示 VGA 输出
make run_real_mode # 保留的 16 位命令行练习
make debug      # 在复位点暂停，配合 config/debug_kernel.lldb
make smoke      # 无窗口：既有回归 + E08存储/运行时gate + 许可证材料检查
make binutils-smoke SEED_MANIFEST=... # 显式已准备的GNU Seed，临时盘客体验收
make clean      # 只删除 build/，包括验证日志
```

内核调试控制台命令：

- `help`、`mem`、`halt`。
- `guo`：Guo YePeng 的仪式性问候；`joke`：一条确定性冷笑话；`about`：版本与致谢。
- `alloc` / `free`：分配或释放一个 4 KiB 物理页。
- `vmtest`：页分配 → 映射 → 写读 → 解除映射。
- `run`：启动 heartbeat/spinner/receiver/sender/probe/quitter/supervisor/files
  八个 ring3 任务，演示定时抢占、IPC、退出、用户故障隔离、资源回收与文件服务；
  之后由 supervisor 的 `sup> ` 接管串口，不再返回内核控制台。若 1 秒无输入，
  旧演示任务会自动停止，避免 `A`/`ping` 淹没提示符。
- supervisor 命令：`ps`、`kill <pid>`、`images`、`exec <image> [args]`、
  `spawn <image> [args]`、`wait <pid>`、`stats`、`primtest`、`elftest`、`help`；
  文件命令：`ls`、`cat`、`stat`、`rm`、`edit`、`filetest`、`sync`、`exec-file`。
- `exec libc_hello` 运行 newlib 示例：`printf`/`malloc`/`strcpy`/`puts`，退出 7。
  libc 程序用 `scripts/user_build.py` 的 `libc_programs` 显式启用。
- `edit note.txt` 用原始行模式编辑（正文不经过分词器）；`:wq` 原子保存，
  `sync` 落盘，`cat note.txt` 查看。`make disk` 创建的工作盘在重启后保留内容。
- 新工作盘默认FAT32、ASCII LFN/目录，不再限制4文件/24KiB；旧FAT16盘仍兼容。
  挂载失败报错，不格式化、不退回RAM。
- 在 `sup> ` 输入 `exec demo hello` 可验证参数和退出码 42；`exec spin` 可单独按 Escape 取消。
- `pf`、`gp`、`ud`、`div`、`df`：故意触发 page fault、#GP、#UD、#DE、double fault，
  用于检查 panic 输出；触发后 CPU 停在 HLT。

实模式练习仍用 `help`、`about`、`clear`、`halt`，ASCII 小写输入，最多 63 字节。
两套控制台都是轮询串口，适合逐字输入；暂不保证高速粘贴或大批量输入。

可覆盖工具路径：`make smoke NASM=/path/to/nasm QEMU=/path/to/qemu-system-x86_64`。
默认镜像只读且网络关闭。只使用专用镜像，不安装到宿主磁盘。

工作盘创建、ATA/FatFs、同步与恢复边界见 [E07 工作盘](docs/e07_persistent_work_disk.md)。
结构、启动契约、异常/内存边界和 UEFI 引入时机见
[架构与启动](docs/architecture_and_boot.md)。受限 C++ 规则见
[cpp_subset.md](docs/cpp_subset.md)。彩蛋（Guo YePeng 横幅、`guo`/`joke`/`about`）只输出文本，不影响错误语义，
可在 `config/x86_64_bios.json` 将 `easter_eggs` 设为 false 后重建关闭。
C 库接入、SSE 上下文和 POSIX 边界见 [E06 libc](docs/e06_libc.md)。
命令逐条说明见 [命令使用手册](docs/usage/index.md)。验证结果和下一步以
[当前状态](docs/state.md) 为准。

想写第一个用户程序，见 [给朋友的快速开始](docs/friend_user_program_quickstart.md)。
用户态装载、初始 ABI 与导出的 `build/sdk/` 见 [E04 SDK](docs/e04_loader_sdk.md)；
文件服务协议、打开实例与原子保存见 [E05 文件服务](docs/e05_file_service.md)；
持久工作盘、ATA/FatFs 与同步/恢复见 [E07 工作盘](docs/e07_persistent_work_disk.md)。
普通程序在客体内解析和执行；`exec-file` 从工作盘文件装载，普通 `exec` 仍用只读启动模块。

自研新代码采用 Apache-2.0；历史 MIT 和第三方许可保留。见 [许可证管理](docs/licensing.md)
和 [NOTICE](NOTICE)。E08 的存储/运行时/工具链/验收合并见
[E08 总览](docs/e08.md)，全部文档入口见 [文档索引](docs/README.md)。
Qt为GUI主线，SDL为次选；分阶段移植与独立验收见[计划](docs/xos_plan.md)的
E13–E20/G系列，当前没有Qt/图形实现。Qt Widgets/QML 的未来移植评估见
[讨论备忘](docs/qt_port_assessment.md)，尚未开始 Qt 实现。
