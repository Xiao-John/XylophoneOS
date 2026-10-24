# XOS 命令使用手册（索引）

本目录是宿主侧使用文档，面向内核调试控制台、用户态 supervisor 和实模式练习。
客体有 E07 的 FAT16 工作盘、E06 的 newlib C 库与 `sup>` 文件命令；正常
`sync` 后重启内容仍在。但工作盘只放用户文件，不能用命令打开这些 Markdown；
请从宿主阅读。

## 控制台与入口

| 控制台 | 入口 | 提示符 | 输入 | 阶段 |
|---|---|---|---|---|
| 内核调试控制台 | `make run` | `xos64> ` | COM1 轮询 | E02–E07 |
| 用户态 supervisor | 内核控制台输入 `run` | `sup> ` | SDK 输入句柄 | E04–E07 / 0007–0010 |
| 实模式练习控制台 | `make run_real_mode` | `xos> ` | COM1 + BIOS 键盘 | 0001 |

内核控制台单向进入 supervisor，不返回。实模式练习是另一镜像，不互相切换。
`make run_vga` 只是显示后端，内核控制台仍从串口读取输入。

## 内核控制台命令索引

| 命令 | 作用 | 需要彩蛋开启 | 文档 |
|---|---|---|---|
| `help` | 列出当前可用命令 | 否 | [help](kernel/help.md) |
| `mem` | 物理内存统计与分配窗口 | 否 | [mem](kernel/mem.md) |
| `alloc` | 分配一个 4 KiB 物理页 | 否 | [alloc](kernel/alloc.md) |
| `free` | 释放上一次分配的页 | 否 | [free](kernel/free.md) |
| `vmtest` | 分配→映射→写读→解除的自检 | 否 | [vmtest](kernel/vmtest.md) |
| `run` | 启动 ring3 任务并进入抢占调度（不返回控制台） | 否 | [run](kernel/run.md) |
| `halt` | 停机并进入 HLT 循环 | 否 | [halt](kernel/halt.md) |
| `pf` | 故意触发 page fault | 否 | [pf](kernel/pf.md) |
| `gp` | 故意触发 general protection | 否 | [gp](kernel/gp.md) |
| `ud` | 故意触发 invalid opcode | 否 | [ud](kernel/ud.md) |
| `div` | 故意触发 divide error | 否 | [div](kernel/div.md) |
| `df` | 故意触发 double fault | 否 | [df](kernel/df.md) |
| `guo` | Guo YePeng 仪式性问候 | 是 | [guo](kernel/guo.md) |
| `joke` | 一条确定性冷笑话 | 是 | [joke](kernel/joke.md) |
| `about` | 版本、构建 ID 与致谢 | 是 | [about](kernel/about.md) |

彩蛋由 `config/x86_64_bios.json` 的 `easter_eggs` 控制；关闭后横幅、帮助项和
`guo`/`joke`/`about` 都不存在，输入它们会得到 `ERROR: unknown_command`。

## 实模式控制台命令索引

| 命令 | 作用 | 文档 |
|---|---|---|
| `help` | 列出命令 | [help](real_mode/help.md) |
| `about` | 当前阶段说明 | [about](real_mode/about.md) |
| `clear` | 清 VGA 文本屏并发送串口清屏序列 | [clear](real_mode/clear.md) |
| `halt` | 停机并进入 HLT 循环 | [halt](real_mode/halt.md) |

## Supervisor 命令索引

| 命令 | 作用 | 文档 |
|---|---|---|
| `help` | 监督终端帮助 | [help](supervisor/help.md) |
| `ps` | 任务列表 | [ps](supervisor/ps.md) |
| `kill <pid>` | 监督终止 | [kill](supervisor/kill.md) |
| `images` | 启动模块目录 | [images](supervisor/images.md) |
| `exec <image> [args]` | 装载并等待 | [exec](supervisor/exec.md) |
| `spawn <image> [args]` | 装载后返回终端 | [spawn](supervisor/spawn.md) |
| `wait <pid>` | 收集子任务结果 | [wait](supervisor/wait.md) |
| `stats` | 资源计数 | [stats](supervisor/stats.md) |
| `primtest` | 构造机制边界/回滚检查 | [primtest](supervisor/primtest.md) |
| `elftest` | ELF 边界检查 | [elftest](supervisor/elftest.md) |
| `ls [path]` | 列出工作盘文件 | [ls](supervisor/ls.md) |
| `cat <file>` | 读取并打印工作盘文件 | [cat](supervisor/cat.md) |
| `stat <file>` | 文件大小/版本 | [stat](supervisor/stat.md) |
| `rm <file>` | 删除文件 | [rm](supervisor/rm.md) |
| `edit <file>` | 原始行编辑器 | [edit](supervisor/edit.md) |
| `filetest` | 文件短读/EOF/句柄/容量检查 | [filetest](supervisor/filetest.md) |
| `sync` | 文件与块设备落盘 | [sync](supervisor/sync.md) |
| `exec-file <file> [args]` | 从工作盘文件装载并等待 | [exec-file](supervisor/exec-file.md) |
| `exec-driver <path> [args]` | 显式授权工具驱动构造子任务并等待 | [exec-driver](supervisor/exec-driver.md) |
| `spawn-file <path> [args]` | 从工作盘启动后台程序 | [spawn-file](supervisor/spawn-file.md) |
| `mkdir <path>` | 创建目录 | [mkdir](supervisor/mkdir.md) |
| `mv <old> <new>` | 改名/移动，拒绝覆盖 | [mv](supervisor/mv.md) |

这些命令只在 `sup>` 生效。按空格分词，不支持引号、管道、重定向。行上限
255 字节，程序 argv 最多64项（含程序名），每项最多255字节；argv/env/cwd共享
4页startup，超出拒绝。监督终端行缓冲2047字节，不能代表SDK总参数容量。
工作盘由宿主 `make disk` 显式创建（新盘默认 2 GiB FAT32），`make run` 只打开
已有盘，原 16 MiB FAT16 仍兼容且不会被升级覆盖。支持目录和 ASCII LFN，
每会话 8 个打开、全局 16 个对象锁；没有旧 4 文件/24 KiB 限制。`edit` 的正文行不走分词器，只有以 `:` 开头的行是编辑器命令。
保存/删除后执行 `sync`，看到 `[files] sync=ok` 再停止 QEMU。
进入 `sup>` 后约 1 秒无输入会自动停止旧演示任务 1/2/3/4；调试旧用例可先
`demo keep`，或 `demo quiet` 立即停止。
支持 CR/LF/CRLF 和退格。前台等待时单独按 Escape 终止被等待任务并恢复终端；
Ctrl-C 仍关闭宿主 QEMU。后台 stdin 暂无作业控制，会与终端竞争。

## 内核/实模式通用约定

- 命令区分大小写，只接受小写；不做参数解析，整行必须与命令名完全一致。
- 内核行缓冲最多 63 字节；超长行整行拒绝，退格不能解除溢出锁，直到回车。
  实模式同样是 64 字节缓冲、63 字节内容上限。
- 两个控制台都接受 CR、LF 与 CRLF；支持 ASCII Backspace/DEL。
- 串口是忙轮询，没有中断环形缓冲和流控；适合逐字输入，不保证高速粘贴。
- 真实失败返回真实错误：`invalid`、`out_of_memory`、`ERROR: unknown_command`
  等；不写“永远成功”的占位结果。
- 诊断优先：panic 会先输出 vector/error/RIP（必要时 CR2），然后才停机。
- `Ctrl-C` 是宿主关闭 QEMU 的操作，不是客体命令；`halt` 只停 CPU，不退出 QEMU。

## 维护规则

- 新增或修改命令时，同时更新本索引、对应命令页、相关测试与 `state.md` 交接。
- 内核命令实现：`src/kernel/core/console.cpp`；测试：`tests/kernel_smoke.py`。
- 实模式命令实现：`src/boot/x86/stage_two.asm`；测试：`tests/boot_smoke.py`。
- supervisor：`src/user/programs/supervisor.cpp`、`src/user/loader/`；
  测试 `tests/process_smoke.py`，也要维护每命令一页。
- 文档描述实际行为；未实现或未验证的能力必须写明“未实现/未运行”，不能写成已支持。

工具链使用见 [E08-4 GCC C Seed](../e08_gcc_seed.md)：安装白名单、显式exec-driver、
静态sysroot/profile与功能验收命令。G++/target标准库尚未验收。

原生C++工具链见 [E08-5 G++ Seed](../e08_cpp_seed.md)，功能闭环与限制见
[综合验收](../reports/e08_acceptance.md)。
