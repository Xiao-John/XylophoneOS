# 0047：Dash C1实现与真实验收过程

2026-10-25（Asia/Shanghai）。工作分支feature/dash-c1-c3，原HEAD006d870，
固定上游integration/2026-10-25=4c78b27c8f07eeb69145d85786660689fe2db9df。
从干净线程仓库另建XylophoneOS-dash-c1-c3工作区；未改原目录、日常盘、Release
或localpilot。远端核对时没有新integration提交。保留0a0fbed原型及0046历史。

主负责人串行修改ABI/kernel/libc/Dash、构建与QEMU；子agent仅做只读机制审计、
研究及互不冲突的测试编写。C1必须完整验收后才进入C2，C2/C3目前not_run。

## 实现

- sys54原型审计确认分派可达、单核检查入睡原子；修正每次端点释放均广播，
  避免等待token被关闭但同方向别名仍存活时永久睡眠。旧token不复用。
- sys55有界前台流水线、sys56有权直接子任务取消、sys20完成查询、sys34自身route
  查询；共享头自动导出SDK，新增ABI见e04_loader_sdk.md。未改文件服务wire ABI。
- 4段external NCMD流水线并发spawn后收集，端点及时关闭，顺序重定向覆盖管道默认，
  失败取消/收集部分任务；备份FD使用>=10的CLOEXEC描述符，异常恢复upstream栈。
- Escape在构造前登记active，取消锁存覆盖“child运行而尚未发布列表”的窗口；
  不增加POSIX信号/作业控制。缺命令127、其他spawn失败126、取消137、正常末段状态。
- libc pipe等待不持FD全局锁，对象lease保活；拒绝未实现F_SETFL，正确区分pipe isatty。
- build_dash显式绑定cross as/ld，仅影响目标编译，避免mac宿主生成器链接器被污染。

C1限定external-only；参数展开在父环境进行，算术展开副作用的完整隔离仍属C2。
不声称fork、pipeline builtin/function、命令替换、here-document或exec已实现。

## 已执行与失败修复（最终冻结回执待追加）

宿主：GCC/G++16.2.0、Binutils2.47.20260726、NASM3.02、QEMU11.1.2，
QEMU pc-i440fx-10.0/TCG/qemu64/512M/1CPU/无网络。各manifest含实际命令与工具哈希。
工作盘仅临时512MiB FAT32或SHA核验发行包提取的独立盘。

初始WIP完整构建通过1f671d83a6979f0e；首次真实65013字节3段流水线导出逐字节一致。
专项attempt1/2因kernel trace插入UART载荷导致过严字符串断言失败，修为移除明确
kernel诊断后比较原始载荷（完整二进制比较始终未放宽）。attempt3发现真实取消竞态：
Escape在第二段装载期间杀Dash，按上文active/cancelled修复。

build1e3df089e3c4639a、Dash b03450a8db8cca57098ac7fd6ed78e0960f2efce6d7038f0aeaa3fc1d0f14f6e：
- tests/dash_c1_smoke.py专项23项passed；131109字节四段流水线由guest逐字节验证，
  sync后离线导出与独立宿主参考逐字节相等；短写真实发生。资源[129833,2,0]恢复。
- tests/dash_c1_threads_smoke.py三轮passed；两个reader、满写、64轮race、EOF/EPIPE、
  raw关闭等待token且保留同向child别名、join/abort以及线程/页基线恢复。
- 中间产物/失败报告保留build/c1_*、dash_c1_attempt{1,2,3}_report.json，最终结果
  以随后完整源码重建回执为准，不把该初步结果视为完整C1 Gate。

正在进行：最终build、Dash A/B0/B1/B2、线程/newlib/C++、进程/文件/持久化、
原生GCC/G++、CPython回归。未运行项目不能写passed。无旧随机大型压力。

CPython3.14.9官方source下载SHA256核对为source_lock指定e02d9ac2…；
GCC16.2.0本地原包为e6738e29…，线程SDK新构建使用独立解压副本与已验newlib前缀。
未来集成：新增sys54–56需其他ABI分支避让；xypm/files wire未改变、ISO容量未改变、
Qt/SMP/异步信号仍未提供。C2计划选单线程eager-copy fork，需认证的文件会话克隆、
Client子PID重绑定、权限与有界嵌套；C3真实exec需地址空间原子commit及FD继承。


## 2026-10-26 C1最终冻结：passed

源码实现f19c02d、pthread/libc测试ed65bf8；验证runner增加UUID证据子目录，避免重复
export覆盖旧证据。最终build `f62f20ef40b19677`，xos.img SHA256
`c95dec12e3a17e2e387d793e8ce4b7fdc98d47d7e8eb43aff8e1a5c6e433a545`。
Dash SHA256 `b03450a8db8cca57098ac7fd6ed78e0960f2efce6d7038f0aeaa3fc1d0f14f6e`。
完整回执与各报告在docs/reports/dash_c1_20261026/，本机镜像/SDK/ELF冻结于
build/dash_c1_frozen/。131109字节流SHA256为
`46d2d9b2b18193a5f5b44b0f5bf41b2f0f6cc493220d2732d32908d0e098891e`，全部字节相等。

C1专项25项；机制线程探针7组/3轮；pthread管道5组/3轮；进程13、文件8、线程15、
pthread/newlib10、C++10、CPython T3-PY5、持久化4、原生GCC/G++6、Dash A15、
B0/B1 7、B2 6及许可材料检查passed。各测试真实命令/输入/输出/资源见报告；
资源基线[129833,2,0]，占槽故障场景先回占槽基线再清背景回原基线。
C1主runner初次全回归在export阶段遇已有证据文件（客体用例全部已过），
修正UUID目标后仅重跑受影响C1专项，其他14个回归结果保留，无伪通过。

CPython宿主引导构建第一次因端口GNU group链接选项在Darwin失败；仅在隔离
host_build/Makefile去掉该选项后构建同版本3.14.9，再设置COMPILER_PATH指向
显式cross as/ld完成target构建；target源码未改，最终T3-PY5/5真实客体通过。
Sbase从官方仓库取得并checkout固定c546c3a、按source_lock逐文件验SHA后构建。
无远端推送/合并或Release变动。下一阶段C2开始，不借C1回执宣称C2/C3通过。
