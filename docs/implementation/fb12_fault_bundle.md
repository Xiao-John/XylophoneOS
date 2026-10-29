# FB1/FB2：用户态故障包与离线定位

验收基线：本地 FB0 提交 `be1c21f`；其相同文件内容已由 PR #15 合入主线。
本组实现直接由 xsh 启动并等待的文件 ELF 的受限故障报告与离线定位。
格式和设计边界见[FB0契约](fb0_fault_bundle_contract.md)；验证及未运行项见
[0081工作记录](../work_log/0081_fb1_fb2_fault_bundle.md)。没有新增内核 syscall。

## 客体使用

在已有 `/bin/fault.elf` 的专用工作盘上：

```text
xsh> diag /bin/fault.elf
[wait] pid=... kind=faulted code=0 vector=14 address=1048576
[fault-bundle] saved /FAULTS/<32位十六进制运行ID>
```

`diag <文件或PATH中的程序> [参数...]` 使用既有 xsh 直接子进程；普通退出和 kill
不生成故障包。先输出原程序结果，再尝试保存；失败显示 `not saved; result unknown`。
路径、命令行、环境、内存、栈、TID和通用寄存器默认不进入包。该入口不自动覆盖其他
父进程的子进程或无父进程的服务。初始化、装载、哈希和服务故障均保持原错误，不伪报成功。

dash 可通过独立程序 `xos-diag` 显式启动和诊断直接子进程：将系统构建产物
`user_xos_diag.image.elf` 安装到工作盘 `/usr/bin/xos-diag`，以具有启动权限的
`exec-driver /usr/bin/dash ...` 启动 dash，然后运行 `exec xos-diag /bin/fault.elf`。
`exec` 替换当前 dash 并保留已有启动权限；普通外部命令不继承该权限，故不能直接运行
`xos-diag` 并期望返回 dash。
程序返回目标正常退出码的低8位；故障或取消返回128，找不到程序返回127，启动失败
返回126，等待失败返回125。目标使用固定 PATH 环境；目标自身继续启动的子进程不自动
收集。该独立入口不提供通用 POSIX 重定向、当前目录及环境继承保证。

装载器在验证和映射ELF时持有同一只读文件句柄；独立SDK函数在同一实例读取完整文件
并计算SHA-256后才使用原加载路径。读取失败拒绝启动；关闭失败也不启动。旧的
`spawn_options` 结构不变，SDK manifest 单独登记诊断能力，内核和 syscall 编号不变。

成功包由 `report.json`、`image.json`、`context.json`、`manifest.json` 组成，字段、
上限和 unknown 语义以FB0 v1为准。run ID来自 `sys_random_bytes`，失败时不以固定值、
PID或时间替代。程序先分别写入并关闭三个内容文件、sync，再写临时manifest、sync、
rename为最终manifest并再次sync。任何写/关闭/同步/rename失败都不报告成功；最终
rename后的sync失败仍是结果未知，不能推定目录一定不存在或已持久化。中断可留下
不完整目录，须显式处理；不会自动删除用户文件，也不承诺任意断电安全。

`/FAULTS` 下顺序检查现有目录，候选上限为16包和2 MiB；满额、包含无法检查的内容
或目录不可访问时拒绝新建。这个检查适用于单个xsh的顺序操作；当前FAT文件服务没有
把该目录锁成私有命名空间，其他进程并发修改可能使全局配额检查失效。FAT权限和目录
名不提供保密或可信身份，不要把报告目录当作授权边界。生成的文件不会自动上传。

## 离线导出与符号定位

先正常 `sync` 并关闭QEMU；在宿主上使用已有 `scripts/work_disk.py` 从**专用工作盘**
将该目录的四个文件导出到一个本地目录。不可在QEMU仍打开工作盘时使用该离线工具。
给定与客体实际运行ELF对应的带符号ELF，先生成绑定，再执行定位：

```sh
python3 scripts/fb2_bind_symbols.py RUNNING_ELF SYMBOL_ELF binding.json
python3 scripts/fb2_symbolize.py REPORT_DIRECTORY --running RUNNING_ELF \
  --symbols SYMBOL_ELF --binding binding.json
```

绑定工具将带符号ELF复制到临时目录，以 `x86_64-elf-objcopy --strip-debug` 剥离，
只有与运行ELF逐字节一致时才创建绑定文件，已有绑定文件不会被覆盖。定位工具校验
四文件布局、无链接、UTF-8/JSON、版本/字段/上限、run ID、内容摘要、运行ELF摘要和
符号ELF摘要；它再次验证剥离结果、x86-64 ET_EXEC和指令地址落在可执行段，再调用
`x86_64-elf-addr2line`。不匹配、未解析或格式错误返回失败，不按名称猜测符号。
本组只实现故障指令定位，不从RIP凭空生成调用栈。文件哈希和匹配关系不是签名，不
证明报告来源可信；共享前由用户检查包含的地址和程序摘要。

## 当前资格与边界

实际系统/SDK/镜像、测试夹具、失败项和哈希以工作记录及冻结回执为准。正常sync、
重启、导出和符号定位分别有客体/宿主证据；满盘、随机数不可用、quota、真实块写EIO
和宿主逐步故障注入分别验证。尚未覆盖内核panic、任意突然断电、硬件扇区撕裂、
服务自动恢复、全系统收集、真实设备、任意ELF类型或全量压力；不以文件存在冒称
文件持久化成功。FB3寄存器/栈/日志和FB4包分发均未实施。
