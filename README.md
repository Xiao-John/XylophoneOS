# XylophoneOS / XOS

给自己和朋友玩的独立操作系统：x86-64、BIOS 启动、NASM + 受限 C++ 微内核，
目标是能在系统内编辑、保存、编译和运行程序。

开发前读 [开发纪律](docs/Discipline.md)、[当前状态](docs/state.md)、
[项目宪法与当前登记](docs/xos_plan.md)。

## 当前发行：0.0.1-1026

[XylophoneOS Revival version 0.0.1-1026](https://github.com/Xiao-John/XylophoneOS/releases/tag/v0.0.1-1026)

下载 images 包和 SDK，安装 Python 3 与 QEMU 后：

```sh
python3 launch.py
```

在 `xos64>` 输入 `run` 进入 Xshell；`dash -i` 进入 dash，`python3` 进入交互式
CPython。install ISO 首次启动会自动把 dash 安装到工作盘，新工作盘本身不预装
dash。

本次发行包含：

- 64 位内核、多任务、进程隔离、单核多线程与用户态 supervisor/files。
- 可启动 install ISO；FAT32 工作盘、目录、编辑、保存和重启恢复。
- xsh 与 dash：流水线、子 Shell、命令替换、Here-document、exec 和 Make。
- 原生 GCC / G++、GNU Binutils、Make；XOS 内编译运行 C / C++。
- CPython 3.14：交互终端、线程、JSON、zlib / gzip / ZIP 和离线 Python 包。
- xypm 离线包管理与独立 C / C++ SDK。

发行说明见 [0.0.1-1026](docs/releases/0.0.1-1026.md)，构建与验收证据见
[docs/project_overview.md](docs/project_overview.md)。
上一次发行 [0.0.1-1024](docs/releases/0.0.1-1024.md) 保留为历史版本。

## 从源码构建

```sh
make build        # kernel、xos.img、file-backed/install ISO、SDK 与 manifest
make dash         # 构建 dash
make install-iso  # 构建带 dash payload 的 install ISO
make license-audit
make smoke        # 串行跑既有回归与许可材料检查
make run          # 启动 install ISO（需要已有工作盘）
make run_file     # 启动无 dash payload 的 file-backed ISO
make run_iso      # 旧嵌入 kernel ISO，仅兼容
make run_floppy   # 旧 1.44 MiB 软盘路径，仅兼容
make disk         # 新建 FAT32 工作盘；dash 由 install ISO 安装
make clean        # 只删除 build/（含验证产物）
```

工具链默认使用已准备的 `x86_64-elf` GCC/G++ 16.2.0 和 NASM；可用
`make smoke NASM=... QEMU=...` 覆盖路径。镜像只读、网络关闭，不安装到宿主磁盘。

## 系统能力

BIOS 启动后进入 x86-64 C++ 内核：E820 物理页管理、异常处理、串口控制台、
ring3 用户任务、每任务地址空间、PIT 抢占、IPC、用户故障隔离、资源回收，
以及用户态 `sup> ` 监督终端。输入 `run` 启动演示任务，随后由 supervisor 接管。

- supervisor：`ps`、`kill`、`images`、`exec`、`spawn`、`wait`、`stats`、
  `elftest` 等；文件命令 `ls`、`cat`、`stat`、`rm`、`edit`、`sync`、
  `exec-file`。
- xsh 是原生入口；dash 是可选 POSIX shell。dash C1–C3 已通过管道、子 Shell、
  命令替换、Here-document、exec 与 Make 的受限 gate。
- 客体内可直接使用 `x86_64-elf-gcc/g++`、`make`、`make -B` 和静态 SDK。
- CPython 支持基础 REPL、`input()`、线程、JSON、zlib/gzip/ZIP 和离线 wheel。
- xypm 当前提供宿主候选盘 install/upgrade/remove、归属校验和客体只读查询；
  完整客体维护事务、仓库和签名仍在后续阶段。

命令逐条说明见 [命令使用手册](docs/usage/index.md)，用户程序开发见
[给朋友的快速开始](docs/friend_user_program_quickstart.md)。

## 已知边界

- 仅 BIOS/QEMU x86-64；UEFI、SMP、完整 POSIX、Qt 图形尚未完成。
- dash 不是完整 POSIX shell：后台/信号/终端语义仍有限。
- CPython 没有安全熵、墙钟、socket/TLS、fork/subprocess 等完整 POSIX 能力。
- xypm P2 写入事务/P3 仓库仍未完整交付；签名不等于沙箱。
- 旧全量压力与部分历史回归未在本发行重跑；未跑项不会被写成通过。
- Qt 是未来 GUI 主线，目前没有实现；见 [Qt 评估](docs/plans/qt.md)。

## 文档与许可

- [文档索引](docs/README.md)
- [架构、启动与内存边界](docs/architecture_and_boot.md)
- [线程实现与验收](docs/implementation/threads.md)
- [独立应用与包管理](docs/plans/packages.md)
- [CPython 移植计划](docs/plans/cpython.md)
- [发行与源码材料](docs/releases/source_materials.md)

自研新代码采用 Apache-2.0；历史 MIT 与第三方许可保留。见
[许可证管理](docs/licensing.md) 和 [NOTICE](NOTICE)。
