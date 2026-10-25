# Dash 当前受限支持范围（C3候选）

C1/C2已独立验收，C3已通过中间专项、最终回归进行中，见0047–0049与独立报告。
支持最多4段前台流水线、真实单线程fork隔离（深度3）、builtin/函数/子Shell、
$()与backticks（raw stdout上限1MiB）、Here-document（引用/展开/<<-与大正文）、
带完整32FD/CLOEXEC的当前SDK v3目标exec；不是完整POSIX Shell。Shell用户重定向
仍限定0–2，标准C exec机制保留0–31。argc/env各64；spawn单串255、exec单串4095、
startup总16KiB，进程全局8个；资源不足明确失败与清理，不承诺任意长度/深度。

后台、trap/jobs/wait/kill等信号/作业内建继续明确拒绝；取消为前台Escape机制，
没有异步POSIX信号、SMP或线程profile fork/exec承诺。旧静态ELF可普通console spawn；未知/旧目标继承普通文件stdio明确拒绝，
显式exec未带`.xos.exec`标记的旧CRT返回ENOTSUP，不丢FD后继续冒称兼容。
正常外部命令仍走已验spawn；`exec`内建和Make后端才使用真实替换。

直接脚本兼容由Dash在用户态处理：无shebang或/bin/sh、/bin/dash、/usr/bin/dash
且无额外interpreter参数的文本可fork后exec当前Dash；其他shebang明确失败。
不创建/bin/sh文件别名、不替换Xsh/default Shell。Make选定sbase固定c546c3a的
显式-B串行profile，详见make_subset.md；没有增量时间戳/并行/GNU Make全兼容声明。

以下保留A/B0/B1/B2历史回执，旧拒绝项已被新阶段支持替代，不表示当前又禁用了它。

## A/B历史范围与证据

2026-10-25。Xshell/xsh 继续是原生入口；dash 是独立用户程序，不替换 supervisor，
不修改默认启动，不安装 /bin/sh 别名。用户以后可以选择自己的使用环境。

## B0/B1已验收

- 新增最大3层的显式构造权委派；非supervisor只能把严格更小的深度交给
  自己尚未启动的直接子任务。旧`grant_spawn=true`的一层直接构造权保留。
- Xsh对裸`dash`启动显式给深度2；dash用户态profile只对固定GCC/G++ driver请求
  委派1层。内核不看文件名/PATH；cc1/cc1plus/as/ld不能继续委派。
- `exec-driver /usr/bin/dash ...`仍只得到旧一层权利；再委派被EPERM拒绝，dash退126，
  已构造的半成品回滚，不产生目标文件。
- 新放行`case`、Shell函数、`.`/source和已有参数展开。它们仍经递归admission检查；
  函数体或sourced文件内的管道/重定向/子Shell不会绕过拒绝。
- 固定sbase commit `c546c3a5724c81cee9a11d816a38ccdf17472129`，提供`cat`/`cp`/
  `mkdir`/`mv`/`rm`窄子集。无递归复制/删除、权限位、符号链接、跨卷改名或
  覆盖目标保证。

最终B gate在XOS客体完成GCC→cc1/as/ld与G++→cc1plus/as/ld，先观测真实语法
错误，再由`cp`替换源码、重译并执行C/C++程序；同一脚本验证case/函数/dot/
参数展开与五个工具。7项检查通过，每组后资源回到`[130336,2,0]`。

## 已验收

dash 0.5.13.5 的原始解析器、展开、变量及控制流，连接 XOS 同步 posix_spawn /
指定 PID waitpid 后端。支持脚本、-c、-i；串口按行输入、退格、空行及 Ctrl-D。
退出 dash 回到 Xshell。A阶段没有改内核；B0只新增有界进程构造权委派。
没有实现fork/vfork，也没有修改终端或信号ABI。

16 项客体验证：引号/空参数、if/for/&&/||、while/算术、外部程序、临时和导出环境、
退出17与继续执行、cd/pwd（含根目录）、缺失命令127、位置参数/shift，五种未支持
构造拒绝（管道/子Shell/命令替换/重定向/后台）、-c 和交互返回 Xshell。
普通组与拒绝组均核对页/任务/完成记录回到基线[130342,2,0]；交互退出也核对基线。
宿主/bin/sh仅产生预期文本，全部功能结论来自XOS客体，不是宿主代执行。

此处没有将上游全部功能当成已实现：当前仍拒绝所有重定向、管道、后台、子Shell、
命令替换等未开放AST构造；case、函数定义与dot/source仅在B1递归检查后开放。检查在当前解析单元执行前递归完成；
多行脚本前面已经成功执行的解析单元不会因后面的拒绝回滚。exec替换、trap、
jobs/wait/kill内建明确报错，times/umask不在命令表。没有信号递送和作业控制。
只有Xsh裸`dash`的明确profile获得两层构造权；不能把它推广为普通程序或
`exec-driver dash`都可继续委派。

## 构建与启动

```sh
make dash                 # 构建 dash；源码包已随仓库放在 src/ports/dash/upstream/
make disk                 # 新建工作盘并预装 /usr/bin/dash
```

`make disk` 依赖 `make dash`，新盘创建后自动导入 dash；已有盘保持不动，可显式运行
`python3 scripts/install_dash.py --disk <disk>` 补装。`make build` 本身不构建 dash。
构建输出独立 `.cache/xos_seed/dash/<fingerprint>/`，manifest记录原包、移植材料、
构建脚本及SDK逐文件摘要。上游文件由固定原包、独立补丁和本地后端共同定义。
宿主只运行mkinit/mknodes/mksyntax；未使用mksignames及其宿主信号表。

新盘已预装 `/usr/bin/dash`；旧盘按上面的 `install_dash.py` 补装后启动 XOS：

```text
xos64> run
sup> exec-driver /usr/bin/dash -i
$ v='hello dash'; printf '<%s>\n' "$v"
$ exit
sup>
```

普通脚本可用`exec-driver /usr/bin/dash /src/example.sh`；需要调用GCC/G++的B1开发脚本使用
裸命令`dash /src/build.sh`，由Xsh的明确Shell profile授予可递减委派深度。原生Xshell当前仍按空格拆参数，
复杂-c字符串应在dash内输入或写成脚本，不把外层引号误认为已由Xshell支持。
新工作盘预装 dash；不替换已公开镜像或标签，已有日常盘不被自动修改。

## 证据与本组修复

dash ELF 962344字节，SHA256
97dd273e34924203bad691df02b3f4f13e3fd448571c84d2065335c05fb7072e。
构建manifest：.cache/xos_seed/dash/439a3c7825a15e276be9/manifest.json。
测试使用相同ELF摘要的71318ebaced6d868b1df目录manifest，报告位于该目录
shell_smoke_report.json。串口build/dash_a_serial.log；测试脚本tests/shell_smoke.py。

系统build 64fcf112f8efc899，输出build/dash_system/。使用发布版supervisor源码，
另修files.cpp路径校验：allow_root时允许单个/通过尾斜杠检查，普通文件路径限制
保持生效。此前`cd /tmp; cd /`第二步失败，此次真实客体通过；未重跑旧压力。
SDK仍使用冻结输入；这是一处files服务修复，不需要重新链接SDK/原生GNU工具。

测试期间另有工作正在整理历史文档并修改supervisor.cpp的PATH行为。没有覆盖这些
改动；64fc镜像绑定发布版supervisor哈希，不把后来PATH修改记作本组客体验收。
本轮没有重建最终共享build/xos.img或宣布最新整个工作区通过验收。

首个参数探针使用printf %zu时，子任务在strlen访问0x9故障；将长度打印改成
有界int/%d后参数与空字符串验证通过。这个格式问题没有独立定向定根因，保留为
SDK/newlib格式支持待查项，不将它误报为Shell参数传递修复。

最终系统build `f3fdb780732801ab`，xos.img SHA256
`b91905f4ec723326a7863c0a6c6aee4d956c24b057c337214ae0116f455b6d3b`。B1 dash ELF 972248字节，
SHA256 `195f49af2471bc5d3b39bea68ebc056ee81416cba0700d0510a87cdbd5a5cfdb`，manifest为
`.cache/xos_seed/dash/39f57f408a4362fda92e/manifest.json`。sbase manifest为
`.cache/xos_seed/sbase/2f27302d19f094f460d2/manifest.json`。B证据为
`build/dash_b_final2/dash_b_acceptance_report.json`；同一最终构建上dash A 16项回归通过，
报告为`.cache/xos_seed/dash/39f57f408a4362fda92e/shell_smoke_report.json`。许可材料检查通过。

B2已由0042完成：files服务管理带引用计数的共享打开实例，spawn按顺序应用文件
动作，`<`、`>`、`>>`、`2>`、`2>&1`及相反次序、builtin恢复、失败继续和嵌套
Escape均通过客体gate。最终build为`911184be3f3c99f6`，B2报告为
`build/dash_b2_acceptance_report.json`；同一构建上B0/B1 7项、进程/SDK 13项与
许可材料检查通过。仍不支持here-document、管道、子Shell、后台和命令替换；
这些属于后续C。xsh的历史搜索/补全/提示符可以独立推进。
