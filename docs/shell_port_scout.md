# Shell 移植勘查：dash 优先，先接 spawn

2026-10-25。范围为源码分析、目标配置与编译探测；没有修改内核、SDK、Shell
执行逻辑或发布镜像。本文的路线是勘查建议，不表示功能已经实现。

## 结论

建议选 dash 0.5.13.5，保留其解析、展开、变量、控制流和内建命令，增加局部
XOS 执行后端。第一批交互/脚本仅运行当前进程的内建命令和同步外部简单命令；
外部命令走真实 posix_spawn + 指定 PID waitpid。先不实现通用 fork/vfork。
随后补描述符传递、阻塞管道和等待，再扩展流水线与隔离执行环境。

这比从零写 POSIX 解析器更符合已有方向，也比为了完整原样 dash 先做 fork、
execve、信号和完整终端更接近可交付。不能仅把 vfork 宏替换为 posix_spawn：
前者返回孩子执行分支，后者在父进程构造启动请求，控制流必须真实改写。

## 实际取得的输入

| 输入 | 来源与实际 SHA-256 |
|---|---|
| dash 0.5.13.5 原始发行包 | https://deb.debian.org/debian/pool/main/d/dash/dash_0.5.13.5.orig.tar.gz ，40090101a2a491f13e901d3d48e90414f26634628b9bfff35ff540363c227a7d |
| dash 对照源码 | https://kernel.googlesource.com/pub/scm/utils/dash/dash/ ，refs/tags/v0.5.13.5；其归档中的 src/jobs.c、src/eval.c、src/exec.c、COPYING 与发行包逐字节一致 |
| BusyBox 1.37.0 | https://www.busybox.net/downloads/busybox-1.37.0.tar.bz2 ，3311dff32e746499f4df0d5df04d7eb396382d7e108bb9250e7b519b837043a4 |

上述为实际下载摘要和关键文件对照，不冒称签名认证或最新版安全审计。
dash 作者站本次 HTTP 空响应、HTTPS 握手失败，故使用 Debian 保留的 orig 包并
与 kernel 镜像 tag 对照。所有候选均只在忽略缓存，不纳入系统或 SDK 分发。

## 两条候选路线

| 候选 | 实际源码发现 | 选择 |
|---|---|---|
| dash | 普通外部命令集中于 eval.c:916 / jobs.c:vforkexec；管道、子 Shell、命令替换另走 forkshell；没有 BusyBox 的 libbb 依赖 | 首选，先替换简单命令的执行边界，分批开放功能 |
| BusyBox hush NOMMU | hush.c:9674 仍使用 vfork；re_execute_shell 负责重执行与状态传递；libbb.h 同时引入 poll、ioctl、mman、socket、termios 等依赖 | 备选；NOMMU 不等于只需现有 spawn，当前收益不足以抵消额外适配 |

这里只编译探测 dash；hush 结论来自真实源码阅读，没有伪报它的目标构建失败。
ash 同属 BusyBox，未独立构建；本轮也未验证其他 Shell，不宣称穷尽所有候选。

## 目标构建探测结果

使用已发布冻结 SDK：build/releases/0.0.1-1024/sdk，内核 build 2c3876e640840ff5。
工具 /opt/homebrew/bin/x86_64-elf-gcc（项目固定 16.2.0）；宿主生成器 CC_FOR_BUILD=clang。
构建目录 .cache/xos_seed/shell_scout/dash_target，与共享 build/ 构建流程隔离。

configure 参数：

```text
--build=aarch64-apple-darwin --host=x86_64-unknown-elf
--without-libedit --disable-glob --disable-tee --disable-memfd-create
```

CC 使用 x86_64-elf-gcc；CPPFLAGS 指向冻结 SDK/include；CFLAGS 为
`-O0 -mno-red-zone -fno-pie -fno-stack-protector`。链接使用冻结 CRT、user.ld、
libxos/libxos_loader/newlib/libm 和实际交叉编译器 libgcc，-nostdlib/static/no-pie，
不使用 macOS 的目标头或库。未传 --enable-static，因为该版本 configure 会覆盖
现有 LDFLAGS，丢失 XOS CRT/链接脚本。

configure 成功。之后实际运行：

```sh
make -k -j2 -C .cache/xos_seed/shell_scout/dash_target \
  CPPFLAGS='-DJOBS=0 -isystem /Users/xylo/Documents/XylophoneOS/build/releases/0.0.1-1024/sdk/include'
```

make 返回 2，得到 14 个顶层 x86-64 目标对象：alias、arith_yacc、builtins、cd、
eval、histedit、mail、main、miscbltin、options、show、signames、syntax、trap。
这只是部分编译，不是完整链接、运行或 Shell 验收。

已显现的编译缺口：

- killpg：newlib 有声明，configure 链接检查未通过，上游 fallback 又定义 static，冲突。
  应关闭未支持的作业控制路径/修正检测，不能声称 killpg 可用。
- 缺少 sys/ioctl.h、sys/mman.h、sys/termios.h 和 arpa/inet.h；先按实际使用处拆分
  可选功能与必要声明。printf 的 htonl 是真实字节序操作，不需要为此加入网络栈。
- lstat 声明/回退和 DT_LNK：当前 FAT 无符号链接，需显式无 symlink profile，
  不能只塞一个类型常量就声称支持链接语义。
- 交叉构建生成器：mksignames 在宿主读取 signal.h，不能直接把 macOS 信号表当
  XOS 信号表。要用目标定义生成数据、由宿主生成器处理；其余生成器也检查目标相关常量。

原始日志与精确环境：缓存下 configure_command.txt、dash_configure.log、
dash_make.log、dash_target/config.log、report.json。源码未修改，SDK 未修改。

## 比编译错误更重要的运行时缺口

1. **创建与等待**：dash 的 vforkexec/forkshell、waitproc 不适配现有 XOS。
   XOS fork/vfork 返回 ENOSYS；waitpid 仅接受正 PID、阻塞等待，不支持 -1/WNOHANG。
   首批同步执行可用指定 PID 路线；多子进程阶段需要非阻塞查询/等待能力。
2. **exec 优化**：eval.c 在 EV_EXIT 且无 trap 时直接 shellexec/execve。必须连这条
   路径一起改接 spawn/wait，再退出当前 shell；不能仅修 vforkexec 就称外部命令完成。
   POSIX exec 内建要求替换当前进程，首批不开放，不能以 spawn 冒充相同 PID 语义。
3. **描述符**：当前孩子按路径重开文件 stdio，不共享打开实例/偏移；重定向顺序、
   fd 别名和 builtin 临时重定向需要真实处理。先完成父 Shell 文件重定向与恢复，
   再开放外部命令的重定向，不能只通过小文件示例。
4. **管道**：8 个对象、每个 4 KiB；当前读写可返回 EAGAIN。必须补可靠等待/阻塞，
   并并发启动所有段，不能先等待第一段完成，也不能用临时文件偷换为流水线。
5. **权限**：shell→gcc→cc1/as/ld 需要受限的构造权委派。首批先验普通外部程序；
   编译器纳入范围时明确启动授权，不能自动向所有孩子递归授予，也不能把可变路径
   字符串当成可信工具身份。可先保留显式 XOS driver 启动入口作为扩展。
6. **信号与终端**：libc 的链接可用不证明 POSIX 信号可递送。dash trap/mask/等待
   要独立适配，首批关闭作业控制与信号 trap，不能做全局永远成功的 signal stub。
   supervisor 等待 shell 时，Escape 的取消目标需验证，不能自动视为取消前台编译器。

## 最短实施批次

### A：真正可用的简单 Shell

- 固定 dash 原包与 upstream 许可，保留解析/展开；关闭 libedit、作业控制、mail 等
  暂不需要的功能，处理真实编译缺口和目标生成器。
- 增加 XOS simple-command spawn/wait 后端，并处理 EV_EXIT 路径。
- 支持交互、-c、脚本文件；验收引号、变量、cd/pwd、export、printf/test、if/for/while、
  顺序与 &&/||、普通外部命令和退出状态。具体开放项由测试逐项确定。
- 入执行前检查不支持的语法/展开：管道、后台、子 Shell、需隔离的命令替换、
  here-document、exec/信号 trap 等明确失败，避免执行到一半才发现不支持。
  不可把上游存在某个语法解释成该功能在 XOS 已可用。
- 保持 supervisor 作为救援；先用已有 exec-driver 启动 shell 取得直接构造权。

### B：开发命令与重定向

- 补 descriptor 传递/共享偏移、按从左到右执行重定向、close-on-exec、失败清理。
- 明确 shell/driver 委派与前台取消，真实运行 gcc/g++ 并收集错误和状态。
- 验收 >、>>、<、2>、2>&1、内建重定向恢复，以及源码/产物同步持久化。

### C：流水线与后续构建工具

- 补阻塞管道、所需等待/子进程管理与 stdin 所有权。
- 优先直接外部命令组成的流水线；pipeline 中的 builtin/函数需要隔离执行环境，
  不得悄悄修改父 Shell 的变量或 cwd。该部分再比较自重执行、状态传递与真实 fork。
- 按真实 Make 配方逐步开放命令替换/子 Shell/here-document；不提前承诺完整 configure。

A 是最小交付，B 才是自然的原生编译体验；C 是独立扩展。按实际缺口决定是否引入
fork，不为“原样运行完整 Shell”先扩大内核范围。不能给未经实施的批次报小时 ETA。

## 验收与目录建议

宿主参考 shell 与目标 shell 对照 argv 字节、退出状态、stdout/stderr、文件副作用。
新 probe 必须覆盖空参数、引号嵌套、短路、PATH 未找到/不可执行的 127/126 区分、
重定向次序与失败恢复；流水线加入大于 4 KiB 数据、提前退出、反复回收和启动失败。
GCC 两层子任务启动、诊断输出、取消、保存重启单列实际客体 gate。

正式实施建议结构：src/ports/dash/{source_lock.json,config,patches,upstream}，
scripts/build_dash.py，tests/shell_smoke.py，docs/shell_subset.md。
普通系统构建不自动下载/重建上游。补丁与原包分开，ISA/固件细节不进入 Shell。

## 许可证注意

dash COPYING 的主体是 BSD 类条款，但其中还单列 mksignames.c 的 GPL-2.0-or-later
及其生成输出说明。必须保留完整 COPYING，逐项核对实际链接/生成材料，不能把
整包简单登记成纯 BSD；新增移植文件按项目 Apache-2.0，修改上游保留原条款。

BusyBox 1.37.0 的 LICENSE 明确为 GPLv2-only。FSF 的兼容性说明指出 Apache-2.0
与 GPLv2 不兼容；现有 libxos.a 含 Apache-2.0 实现，直接静态链接需要另外解决
组合许可，不能仅以“不同进程”解释这个同一可执行文件内的链接。此问题不等同
于要求 XOS 内核改许可证，也不自动禁止将 BusyBox 放在同一系统中。
本轮未引入候选为分发依赖，不更改 XOS 既有授权。

参考：

- https://kernel.googlesource.com/pub/scm/utils/dash/dash/
- https://www.busybox.net/downloads/
- https://www.gnu.org/licenses/license-compatibility.en.html
- https://pubs.opengroup.org/onlinepubs/9799919799/utilities/V3_chap02.html
