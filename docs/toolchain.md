# E01 工具链与构建

## 固定范围

`config/toolchain.json` 固定 GCC/G++ 16.2.0、Binutils 发布版 2.47（实际工具
版本串 2.47.20260726）、NASM 3.02、QEMU 11.1.2，目标 `x86_64-elf`。
`config/x86_64_bios.json` 固定当前架构/平台/固件、内核容量与彩蛋开关。
这是一套宿主运行的 freestanding 交叉工具，不是 XOS 原生 GCC 或 XOS sysroot。

实际宿主为 Apple Silicon macOS，GCC 构建/运行地均为宿主，代码目标为 x86-64 ELF。
已安装 Homebrew 的 `x86_64-elf-gcc` 与 `x86_64-elf-binutils` bottle。
`compiler_configuration.log` 实际配置包含 `--target=x86_64-elf --without-headers
--enable-languages=c,c++ --disable-nls --without-isl`，线程模型 single。

当前不选择 libc，不创建 Linux/POSIX 兼容 ABI，也没有交叉构建原生 Seed。
E04 提供自有、版本化的最小 SDK 与初始进程 ABI。
宿主自带 g++ 不用于生成客体代码。Clang 只用于宿主边界测试与第二 ISA 编译检查，
LLDB 只用于调试；二者不替代 GCC 主线。

## 准备与运行

本机已安装，可直接 `make build`。新 macOS 宿主可用：

```sh
brew install x86_64-elf-gcc x86_64-elf-binutils nasm qemu
make build
make smoke
```

Homebrew 未来可能升级，不能把该安装命令当作永久版本锁。
构建会核对固定版本、target 和 GCC 实际配置的 as/ld 路径，不符合即失败；
需准备匹配工具，或显式评审升级锁文件并重跑验证。支持 `CROSS_PREFIX` 指定工具前缀。
本轮没有从源码重建 GCC/Binutils；配置来源为安装包与工具实际输出，不宣称验证过
源码构建流程或源码压缩包哈希。

首次安装的默认下载源曾连接失败，本机通过单次环境变量使用中科大 bottle 镜像
完成安装，没有改全局 Homebrew 配置。若复用该方式，只对安装命令设置：

```sh
HOMEBREW_NO_AUTO_UPDATE=1 \
HOMEBREW_BOTTLE_DOMAIN=https://mirrors.ustc.edu.cn/homebrew-bottles \
HOMEBREW_API_DOMAIN=https://mirrors.ustc.edu.cn/homebrew-bottles/api \
brew install x86_64-elf-gcc x86_64-elf-binutils
```

## 产物与审计

`make build` 每次由明确选定的源文件构建，输出主线 `xos.img`、练习
`real_mode.img`、带 DWARF 的 `kernel.elf`、`kernel.bin`、链接 map、反汇编和 ELF 清单。
链接使用 `-nostdlib -static`，不使用宿主启动对象、libc 或标准 C++ 库；
要求无未解析符号。编译没有引入宿主头文件，自研头文件位于 `include/xos/`。

`manifest.json` 记录代码与配置逐文件哈希、构建 ID、实际完整命令、工具版本、
GCC/cc1/cc1plus/as/ld/objcopy/nm/ar/NASM 的真实可执行文件哈希、内核符号和产物哈希。
该记录绑定本轮工具和源码，不把版本字符串相同等同于二进制相同。
当前验证同宿主同工具重建产物相同，不声称跨宿主逐字节可复现。

`make libc-audit` 从 `build/sdk` 的实际 newlib 产物生成
`build/libc_audit.json`；普通 `make build` 只复制预构建包，不联网。
`make smoke` 运行八套检查，产生 `smoke_report.json`、
`kernel_smoke_report.json`、`task_smoke_report.json`、`process_smoke_report.json`、
`file_smoke_report.json`、`persist_smoke_report.json`、
`full_disk_smoke_report.json` 与 `libc_smoke_report.json`：

- 实模式 6 项：启动、命令/边界、键盘、清屏、halt、损坏阶段拒绝。
- 内核 18 项：ELF 权限、实际执行模式、BSS/data、页表与 identity 页 W^X、
  IDT/IST、E820 分配边界与 double free、映射往返、控制台、彩蛋、五类真实异常、
  缺 NX 拒绝、启动信息失败边界、第二 ISA 编译、LLDB 符号断点；E04/E05/E07 的详细项见各报告。
- E03 12 项：ring3 启动、PIT 抢占下 heartbeat 存活、IPC 送达、无效句柄/越权/
  超长/坏指针拒绝、用户故障隔离、退出移除、probe/quitter 回收、supervisor
  `ps` 与 `kill`、被杀任务移除、多个 CR3 与 CPL=3 观察。
- E04 13 项：用户态 ELF 解析/装载、argv/句柄、阻塞 wait、故障/终止状态、
  构造回滚、页表权限/guard、Escape、10 次回收稳定等。
- E05 8 项：文件服务启动/列表、短读/EOF/独立打开/容量/无效句柄、
  编辑器空行与连续空格、修改既有文件、文件错误、删除、文件装载执行。
- E07 5 项：第一次启动创建/覆盖/删除+sync、第二次启动验证正文/删除、
  执行盘上 ELF、命名空间满与物理满盘时保存失败且旧文件/缓冲保留。
- E06 3 项：newlib 程序进入 catalog、printf/malloc/string/exit、第二次运行复用。
- 合计 65 项；E08–E12 尚未运行。

六个旧 demo/*.asm 仍是 E03 回归夹具；新的用户程序在 user/programs/*.cpp，
文件服务在 user/services/files.cpp（链接 FatFs R0.16），低层 ATA PIO 在
kernel/platform/pc；文件客户端/编辑器在 user/sdk 与 user/services。
E06 的 newlib 4.6.0 预构建包在 third_party/newlib，libc 适配层在
user/libc；make libc-audit 从实际产物生成依赖清单。
user_build.py 导出 SDK，用同一 SDK 构建真实 ELF，并生成只读启动模块与可信
bootstrap 段清单；`files` 与 supervisor 都走可信 bootstrap 段，内核不解析 ELF。
SDK、用户 ELF、文件服务与 hello 的哈希进入主 manifest。机制分别见
`e04_loader_sdk.md` 与 `e05_file_service.md`。测试依赖 Python 3.10+、Clang 与 LLDB；
本机实际版本记录在报告。

## 调试

第一个终端：

```sh
make debug
```

第二个终端从 XOS 根目录执行：

```sh
lldb --no-lldbinit -s config/debug_kernel.lldb
```

QEMU 仅在 loopback:1234 监听，并从复位点暂停；脚本加载 ELF，在 kernel_main
断下并打印调用栈、启动参数和寄存器。调试器使用 x86-64 解码，复位时的 16 位
固件反汇编不能据此判断正确性；继续到内核断点后才检查 64 位源码。
自动测试使用随机 loopback 端口，实际完成过连接、断点、参数查看、符号栈与 detach。

参考：[GCC x86 options](https://gcc.gnu.org/onlinedocs/gcc/x86-Options.html)、
[QEMU GDB stub](https://www.qemu.org/docs/master/system/gdb.html)、
[LLDB remote debugging](https://lldb.llvm.org/use/remote.html)。
