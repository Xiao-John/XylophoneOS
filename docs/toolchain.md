# 工具链与构建入口

2026-10-27。构建输入以config/toolchain.json、config/x86_64_bios.json与实际manifest为准。
固定目标x86_64-elf、GCC/G++16.2.0、Binutils2.47（版本串2.47.20260726）、NASM3.02、
QEMU11.1.2。宿主交叉工具、XOS原生Seed、目标运行库和原生重建是不同产物。

## 普通系统构建

```sh
make build
python3 scripts/build.py --output-dir build/<task>/system
```

普通构建不下载或重编整个GNU工具链，导出匹配SDK/用户ELF、带符号kernel、镜像和manifest。
新系统输出放build/私有子目录，保留旧资格；共享build排他，禁止根目录清理。
默认运行路径为file-backed安装ISO；legacy软盘/embedded ISO仅在其预算内生成。
已有工作盘不自动迁移；make disk不预装dash，安装ISO携带dash供首次启动安装。

scripts/toolchain.py核工具版本、target与实际as/ld路径；构建进程绑定交叉工具，不把该环境
泄漏给宿主Clang。manifest记录源码/配置、完整命令、工具可执行文件哈希、布局/符号与产物。
同版本字符串不等于同二进制。只验证同宿主同输入重建时，不声称跨宿主逐字节可复现。

## Seed与SDK

- C/C++原生Seed、运行库输入、安装布局和受限验收见[E08](e08.md)。原始Seed不覆盖，
  派生/relink从实际receipt取输入，GCC执行依赖与自举构建依赖分别审计。
- 普通newlib SDK由scripts/user_build.py产生；线程SDK由scripts/build_threading_sdk.py
  独立导出。静态CRT/ABI/profile要匹配，不拿宿主库/头补目标链接。
- NASM处理手写架构汇编，GCC生成汇编由GNU as处理；宿主生成器与XOS程序执行地分开。
- 目标C++已具受限异常/RTTI/TLS/标准库等专项证据；内核仍无libc/libstdc++且禁异常/RTTI，
  两个语言/运行库面不能互相套用。源码边界见[受限C++](cpp_subset.md)。

## 测试、调试与分发

按本次改动运行相关探针，不因文档或元数据变化重复旧全量/压力。第二ISA只编译通用源，
不是另一ISA启动。详细结果和未运行项进入专项回执，旧报告不改绑新源码。

make debug/LLDB入口与config/debug_kernel.lldb用于带符号目标调试；调试器在64位入口后
核对寄存器/符号，复位时16位固件反汇编不作内核执行证据。终端/监督保留救援能力。

SDK/发行打包必须核system manifest、完整文件/目录/哈希、配置与运行库来源；输入与实际
拷贝/成品绑定，不复用旧staging。许可、源码、符号与发行镜像可对应；见[许可](licensing.md)
和[发行/审计摘要](history/delivery_audit.md)。系统内重建与编译器自举均尚未验收。
