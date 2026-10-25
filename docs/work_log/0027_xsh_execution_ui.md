# 0027：Xsh交互与可执行查找优化

2026-10-25。用户授权Xsh升级、可执行文件设计优化及子agent。主端负责整合/构建/
文档；kernel_trace负责日志开关和旧runner入口适配，execution负责候选检查/装载
诊断，ui_cases准备新客体runner。主端复查并修正测试CRT、启动方式和失败路径。

## 已完成

欢迎与xsh>提示符、分组help、type解释命令/别名/路径；前台成功不刷PID/等待/
回收日志，trace on/off可切换。程序输出不被过滤，非零退出/故障/取消仍可见。
PATH检查实际ELF并跳过数据/目录/错误ISA候选；合法ELF改为.txt仍运行；显式路径
不fallback，读取/资源错误中止搜索。预检不创建任务，最终装载仍锁定同一文件。
新diagnosed接口返回失败阶段/code/ELF原因，旧spawn接口保留。内核不加入PATH/
ELF/解释器策略。sys_debug_trace=36仅bootstrap supervisor可设置，driver/普通任务
拒绝；参数first=0/1、second/third=0，错误日志不受其影响。
保留exd和裸命令的既有构造权语义，没有实现dash→gcc进一步委派、fork、执行位、
脚本猜测或默认Shell替换。范围和限制见xsh.md。

## 实际构建与验证

隔离build/xsh_ui构建，ID b508acc417e218b3；kernel.bin 335916字节。
xos.img SHA256 2371b0118ea1499450f49d4801e87238073eec86a45679fad2f25714e087499b。
全部manifest源码摘要与当前文件逐项一致；未替换共享build/xos.img、日常盘、
发布标签或附件，没有操作localpilot。

```sh
python3 tests/xsh_ui_smoke.py --system-dir build/xsh_ui --output-dir build/xsh_ui_acceptance
python3 tests/shell_smoke.py --manifest .cache/xos_seed/dash/439a3c7825a15e276be9/manifest.json --system build/xsh_ui
```

11组新UI/执行gate与16项dash A gate通过，绑定同一系统。UI包括sys36越权拒绝、
静默/trace、显式路径拒绝、三类PATH候选、type、非零17、fault、改扩展名，和无
构造权程序连续20次diagnosed create/-1后仍可检查文件，验证句柄/资源回收。
临时盘和QEMU实例独立。资源基线[130336,2,0]逐组恢复，比旧版固定多6页来自代码/
数据增量，不是逐轮泄漏。报告build/xsh_ui_acceptance/{xsh_ui_report.json,
acceptance_summary.json}及同目录串口，dash报告在439a3目录shell_smoke_report.json。

command.cpp和load.cpp用clang++ --target=aarch64-none-elf分别编译通过，只是通用
代码编译检查，不是第二ISA移植。隔离SDK许可材料/登记摘要检查通过，报告同目录
license_material_report.json；不是库成员法律审计。没有重跑旧全量或压力/soak。
旧runner进入新Xsh时显式启用trace；sup>只读兼容xsh>，普通expect不发命令。
新UI gate直接断言xsh>及默认简洁模式，未降低业务断言。

review发现初版resolver在unreadable后仍继续搜索，已改为立即停止；fstat失败路径
关闭失败也保留真实错误。最终gate覆盖成功/拒绝；服务无法通信时的恢复未验。

## 交接

dash_port_plan.md按B0启动/受限委派、B1构建脚本、B2描述符重定向、C1管道等待、
C2隔离环境、C3兼容收口拆分。优先让dash自然调用真实GCC/G++；不按工具名写
内核特权，不把spawn当exec替换，不把重开路径当共享描述符。B/C本轮未实施。
本组结束，子agent均交付，无编辑占用；未提交推送。
