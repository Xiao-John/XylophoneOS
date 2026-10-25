# Xsh：原生入口与可执行程序

2026-10-25，0027。原生入口仍是Xshell/xsh；dash为可选用户程序。

```text
xos64> run
Welcome to Xshell | XylophoneOS
help: commands   dash -i: POSIX shell   trace on: diagnostics

xsh> type exd
exd: alias for exec-driver
xsh> type dash
dash -> /usr/bin/dash
xsh> dash -i
$ exit
xsh>
```

`make disk` 创建的新工作盘会预装可选 dash；已有旧盘需运行
`python3 scripts/install_dash.py --disk <disk>` 补装。成功前台命令默认仅显示程序输出；非零状态、故障、取消和启动失败仍可见。
`trace on`显示进程启动、地址空间、等待、回收和原有loader/wait详情，`trace off`
恢复简洁输出。内核fault/panic等错误从不受这个开关控制。启动引导与演示任务的
原有输出仍保留；本轮不是新终端驱动、历史搜索或补全实现。

## 查找、判断、装载、运行分开

用户态execution库位于src/user/loader/command.cpp，公共接口execution.hpp。

1. Xsh先处理内建命令与固定exd别名；`type`可以解释其归属。
2. 含斜杠的外部命令只检查指定路径。裸命令按/usr/bin:/bin:/有序搜索；空PATH项
   不隐含当前目录。根目录是当前兼容路径里的显式项，不是通用cwd搜索。
3. 候选分类为missing、directory、executable、not_executable、incompatible、unreadable。
   读取实际ELF字节并复用现有完整装载校验，检查当前ISA、支持的ELF类型/布局等。
   扩展名不参与判断。PATH跳过目录、普通数据和不兼容格式候选，查找后续可用项。
4. 读取/资源错误中止搜索，不以此为理由改跑后面的同名程序。如果没有可用候选，
   保留首个实际拒绝原因；全都缺失则报告not found。显式路径从不fallback。
5. 最终调用spawn_file_diagnosed：open、inspect、prepare、create、map、start阶段
   的错误以结构化数据返回Xsh。预检仅是预览；正式装载重新打开并持有同一文件锁，
   覆盖校验、逐页复制和关闭。选中后的资源/授权失败不会触发另一次PATH选择。
6. 内核只做任务、页表、句柄与生命周期机制，不识别文件名、PATH、ELF或解释器。

“executable”在本轮表示通过当前ELF装载规则，不保证这次一定有资源或授权，也
不证明程序不会崩溃。还没有独立XOS ABI标记/签名或完整跨版本ABI识别；不能把
结构匹配声称为任意同ISA软件的ABI兼容。没有新增执行位、扩展名关联或脚本猜测。
脚本继续显式交给dash；不认识的文件不自动当Shell脚本运行。

## 授权与诊断

exd仍是exec-driver别名，spawn-file等既有语义保留。裸命令的既有driver构造权
行为本轮未改变；文件可装载不等于该权限模型已经完成后续设计。dash→gcc→cc1
的受限委派见dash_port_plan.md，不能用文件名gcc当作内核授权规则。

sys_debug_trace=36是新增窄机制接口：first=0/1、second/third=0，只允许真实
bootstrap supervisor。普通任务即使有driver构造权也不能改全局日志。Xsh启动时
关闭正常生命周期日志；用户可显式打开。没有给日志开关附带进程构造或块设备权。

老SDK spawn API保持返回值与诊断行为；新增diagnosed入口不直接打印ELF内部错误，
由调用者呈现。trace模式保留elf: rejected reason信息，便于既有定向runner适配。

## 使用与验证

普通make build/run重建并使用当前代码。本轮统一构建输出是build/xsh_ui，保留
共享build/xos.img及已发布0.0.1-1024镜像。dash本身沿用已验收的A版ELF；安装到
工作盘的操作必须在QEMU关闭时显式执行，不能覆盖现有文件。

对应gate：

```sh
python3 tests/xsh_ui_smoke.py --system-dir build/xsh_ui --output-dir build/xsh_ui_acceptance
python3 tests/shell_smoke.py --manifest .cache/xos_seed/dash/439a3c7825a15e276be9/manifest.json --system build/xsh_ui
```

新UI runner直接检查xsh>和默认简洁输出。旧runner的sup>仅在只读匹配中兼容xsh>；
需要旧日志的启动入口显式调用expect_supervisor(trace=True)，普通expect不会发命令。
这使历史镜像sup>仍可用于定向测试，不把旧镜像和新行为混为同一份验收。

行编辑接受UTF-8，按码点退格并按显示宽度擦除；非法UTF-8整行拒绝。文件名/路径
仍是ASCII（U2未做），VGA不渲染UTF-8，原生输入法未实现。
当前不提供type --all、动态PATH赋值、cwd提示、通用alias、引号或完整Shell语法；
继续把脚本工作交给dash。后续xsh体验改进可独立推进。
