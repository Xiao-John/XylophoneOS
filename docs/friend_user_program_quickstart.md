# 给朋友的 XOS 用户程序快速开始

2026-10-25，0032更新。普通用户程序独立开发，不需要修改XOS源码或加入启动镜像。
已有原生GCC/G++与宿主SDK。0035已交宿主xos_app构建/打包；0044的xypm已支持宿主候选盘安装/升级/卸载和
客体只读查询。命令统一为xypm，`.xpk`格式保留；见[包管理命令](package_management.md)。

## 开发方式

| 方式 | 编译在哪里 | 交付 |
|---|---|---|
| 宿主SDK | 宿主x86_64-elf交叉工具链 | 独立ELF，显式导入盘 |
| 原生开发 | XOS的GCC/G++ | 工作盘源码→/out产物→执行 |

发行0.0.1-1024提示sup>，新开发镜像提示xsh>；两者都支持exec-driver/exec-file。
新Xsh正常成功默认简洁，非零/故障仍显示。dash可选，不是编译程序的必经入口。

## 新的独立项目工具（P0已实现）

在XOS仓库目录，用`python3 scripts/xos_app.py init /tmp/my_xos_app --id friends.my_app`
创建新项目，再用build/check/pack指定完整冻结SDK；完整命令见[包管理P0](package_management.md)。
项目位于仓库外，不修改系统程序清单。工具产出build_receipt.json和.xpk，xpk只
代表可校验分发材料，当前安装仍走下文离线桥。发行compile.py也继续支持：

## 宿主独立项目

下载发行SDK解压到独立目录，另建自己的hello_friend/main.c：

```c
#include <stdio.h>

int main(void) {
    puts("hello from my friend");
    return 0;
}
```

在自己的项目目录，SDK替换为实际解压路径：

```sh
SDK=/absolute/path/to/xylophoneos_revival_0.0.1-1024_sdk
python3 "$SDK/compile.py" --c main.c -o hello_friend.elf
```

C++省略--c并传入main.cpp，范围以SDK回执为准。需另行安装x86_64-elf-gcc/g++和
配套工具，可用XOS_CC/XOS_CXX指定。宿主clang/g++生成的macOS程序不能当XOS ELF。
compile.py选择CRT/链接脚本/静态库，普通应用使用main，不必写底层xos_user_main。
保留manifest、目标库来源和ELF摘要；新线程SDK将是独立profile，不混旧库新头。

## 现在的安装方式：显式离线导入

已有`.xpk`包时优先使用[宿主xypm候选盘事务](package_management.md)。以下是
单个开发ELF的文件桥路径，不登记包归属。使用scripts/work_disk.py；先关闭使用该盘的
QEMU，选择已有工作盘的独立副本。只操作普通镜像，不操作真实磁盘。以下从XOS
仓库目录执行，WORK/APP替换为实际绝对路径：

```sh
WORK=/absolute/path/to/test_copy/work_disk.img
APP=/absolute/path/to/hello_friend/hello_friend.elf
python3 scripts/work_disk.py "$WORK" import /out/hello_friend.elf "$APP"
```

发行盘已有/out；自建盘没有该目录时，先执行：

```sh
python3 scripts/work_disk.py "$WORK" mkdir /out
```

import拒绝覆盖目标；重测用新文件名或专用新副本，不删除日常盘。首次可能编译
宿主FatFs传输程序，开发agent遵守共享build排他规则。这只是文件复制，没有包
归属或升级事务。让QEMU使用刚才的副本，启动配置以所用启动器的--help为准；
发行launch.py默认使用其目录里的work_disk.img，不能导入副本后误启动原盘。

进入用户终端运行：

```text
exec-file /out/hello_friend.elf
```

应打印hello from my friend并回终端。普通程序不用exec-driver；只有确需构造
子进程的驱动工具才要显式构造权。扩展名不决定ELF兼容性或运行授权。

## XOS内写、编译、运行

发行盘已有编译器、/sysroot、/src、/out，其他盘按工具链回执安装。进入edit后
粘贴上面的C正文，以:wq保存，再执行后续命令：

```text
edit /src/hello_friend.c
exec-driver /usr/bin/x86_64-elf-gcc -static --sysroot=/sysroot /src/hello_friend.c -o /out/hello_friend.elf
exec-file /out/hello_friend.elf
sync
```

C++改x86_64-elf-g++和.cpp。编译器启动cc1/as/ld，故用exec-driver；hello只需
exec-file。最新dash B0/B1还可走已配置的GNU启动链，见shell_subset.md；不要将
该能力归到原发行。编译失败时旧ELF可能仍在，不能误运行旧产物当作本次成功。
正常sync后再关机/重启核对保存内容。

## UTF-8与现有解释器

最新开发镜像的Xsh/dash已有UTF-8行编辑、按码点退格和argv字节传递（0033）；
串口可原样输出中文。文件名/目录仍受ASCII限制，VGA/locale/输入法未随此完成。
因此可以写中文字符串，项目/资源/存档路径先用ASCII，不混淆文本和路径能力。

CPython 3.14.9的PY0已通过（0030），可复用其已安装解释器执行已验脚本子集；
REPL/input和PY1完整路径规则仍待后续gate，不据Shell通道完成推导Python输入
也已通过。Open Adventure正在独立移植，构建方式以[该计划](adventure_port_plan.md)
及其回执为准，包管理不会要求把第三方程序塞进系统镜像。

## 能力和常见问题

- 当前静态ELF64/x86-64，不兼容任意同ISA Linux程序、动态链接或.so。
- 已有newlib文件/目录、动态堆、FP/SIMD、静态TLS与受限C++运行库；不等于完整
  POSIX。多线程仍是E13-T计划，带pthread.h不代表已实现pthread。
- 当前开发ABI最多64参数、每项256字节，用户页总限256 MiB、主栈128 KiB；旧
  发行实际限制以其SDK/系统回执为准，新文档不改变旧二进制能力。
- 盘上ELF流式装载不受128 KiB启动模块限制，仍检查段布局/页预算等。
- 文件找不到先检查启动的盘与安装路径；构建成功不等于安装。装载拒绝检查SDK/
  ELF/静态库和内存。image busy时关闭旧实例，不绕过锁。
- Escape可监督取消前台程序，不回滚文件写入；检查数据并sync。

独立应用可选自己的许可证；分发保留实际链接/携带组件的适用声明和材料。XOS
自研默认Apache-2.0不覆盖你的独立项目，也不改写newlib/GNU条款。
原compile.py模式有0023/E08证据；0035新增P0宿主16组及C/C++包payload客体gate。
没有重跑旧测试或替换0.0.1发行。
机制见[E04 SDK](e04_loader_sdk.md)、[E08工具链](e08.md)、[Xsh](xsh.md)。
