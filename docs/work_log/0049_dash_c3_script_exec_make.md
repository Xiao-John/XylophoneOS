# 0049：Dash C3脚本、exec与Make

2026-10-26；feature/dash-c1-c3，固定integration4c78b27，C2 Gate冻结6f82d70后开始。
主负责共享ABI、libc/loader/Dash/launcher、整合/串行构建/QEMU；子agent分别做
kernel exec、匿名files、固定Make端口、独立专项夹具。保留C1/C2冻结SDK/镜像，
不改日常盘、Release、上游main/integration、localpilot或他人工作区。

## 实现与明确范围

- exec用专门不可运行stage与单一commit，PID/TID/父/完成记录/FD身份保留，旧VM
  切换后才回收；新CRT恢复完整32FD分组/CLOEXEC，原file session打开实例保留，
  opaque IPC tokens轮换避免旧回复跨image匹配。完整契约见e04_loader_sdk.md。
- 显式exec只接受当前CRT `.xos.exec`能力标记；旧静态GCC/CPython普通spawn兼容，
  不把新v3表交给不懂它的旧init后误称FD继承成功。普通EV_EXIT仍spawn，真实exec
  来自exec内建/标准C接口/Make recipe后端。execvp不越过首个ENOEXEC/ENOTSUP候选。
- HereDoc通过真实匿名打开实例填充/seek0/共享seal只读，最后close/kill删除；正常
  path不能访问保留8.3临时名，排他创建不覆盖碰撞，跨崩溃未知所有者不扫描删除。
- Make版本固定sbase c546c3a，原始5C+make.h+LICENSE逐SHA保留；Apache独立backend。
  必须-B并打印无mtime的always-build说明，显式串行依赖/变量，图visiting/done检查
  环与diamond；拒绝-j/-q/-t/-r、missing-f、$?、+recipe、推导等未实现路径。
  Xsh bareDash深度3，Dash固定make profile2，Make fork/exec recipeDash保2，
  recipeDash→GNU1→子工具0。kernel不匹配文件名、maxdepth仍3，legacy driver授权不变。
- SDK manifest公开startup/exec能力和限制；线程SDK继续拒绝fork/exec。没有POSIX
  async signals/job control承诺，Escape实际取消前台组；Make将SIGKILL/转递137保留
  为不可被-i/-/IGNORE掩盖的终止状态，partial outputs保留并诊断。

## 已实际执行的中间结果（最终冻结待追加）

构建候选ef0ecca5cbb4fa88，kernel380988B。exec专项14个mode通过：同PID/TID、
CR3/堆/栈/TLS/FPU替换、全32FD/CLOEXEC/共享offset、空/LF/TAB/1024字节参数、
缺文件/坏格式/未标记ABI/PATH首候选/无槽/真实partial-map ENOMEM后旧状态保留。
完整记录build/dash_c3_exec_attempt3_report.json，使用实际QEMU11.1.2 TCG单核512M。

HereDoc/Make首个完整pass为build/dash_c3_attempt3_report.json：62项，65,573字节
正文和引用/展开/<<-等与host参考完整字节相等；匿名16槽/共享seal/close/fork/kill
与碰撞文件保留；真实GCC/G++项目编译/链接/执行、重建/错误/HereDoc修复、Make
选定正负行为/取消。实际客体将sbase Make真实4C+backend C++编译链接成/out/make
并用它重建项目和运行产物；ELF909504B，SHA256
8fee08fad67ed91e9052a7ad4ad5935d2be84326ce84acdc01029b7c6b2ef228。
资源始终回[129826,2,0]；不是宿主Make或预编译产物代执行。

中间失败：
1. Make backend误用普通SDK不存在的C++包装头、setenv特性宏缺失，改C头与显式
   POSIX特性宏后真正编译通过，保留build/c3_make*及fingerprint失败日志。
2. 原始Dash ELF超过ISO 1MiB payload边界；分离保留debug ELF与strip-debug runtime
   ELF，实际校验entry/PT_LOAD/PT_TLS字节完全一致。runtime约264KiB，未扩ISO容量。
3. exec runner把C3_EXEC_FAILURE（成功失败回滚证明）误匹配为FAIL，收窄负标识后
   重跑；实际missing回滚已正确，未将测试误判当内核修复。
4. Make -i会吞recipe Shell转递的fault退出137，补reserved137不可忽略语义，真实
   fault/取消重跑。正常exit137也强制终止，已明确不是完整POSIX ignore行为。
5. self-build首次旧GCC派生cc1报Arg list too long。旧工具仍有255字节argv/env
   限制（包括长选项环境）；缩短编译FLAGS并用明确C3Self.specs提供真实新SDK
   CRT/link/lib配置后客体自构建通过，未替换/覆盖原/sysroot。

新增explicit exec客体自建Make（权限3→2、后继代码不执行）、旧真实GCC普通spawn
与exec拒绝边界、一次replacement约束及最终完整SDK/旧回归仍在最终验收。

## 集成边界

上游integration重新核对仍4c78b27。新增sys54–61/file op20–22需后续分支避让。
xypm xos_app.py按冻结SDK tree hash严格登记；本新SDK未擅自写入旧profile白名单，
未运行/宣称新SDK包发布兼容。CPython实际重建T3-PY回归，不启用其fork配置；
Qt/SMP/线程fork/exec/任意迟到RPC恢复not_run/unsupported。ISO保持1MiB payload、
512KiB kernel和既有映射上限，runtime ELF减去debug避免侵占容量。这里没有新Release。

最终审计补充：原<=4KiB pipe write在仅有部分空间时可能短写，继承pipe还受console
256字节截断，不能保证多个writer的小写原子性。收口改成等待完整小写空间，并给
sys54增加writer minimum空间参数（0兼容旧any-space）；补双writer/257字节读取
强制不足空间时序的定向客体测试。大write短写与C1 gate保留，匹配SDK重新构建。

原子写收口兼容性复核：用sys11/32 handle高位opt-in原子小写，保留不带flag的旧
raw小/大短写与second0 any-space配对语义；新libc自动选择。定向测试额外要求
旧raw 512请求在257空间仍返回257，带flag则EAGAIN，避免破坏已冻结ABI。

最终全套首次执行：原子写、exec15、C1/C2、线程/文件/进程/CPython/GCC/G++/持久化、
Dash A/B0/B1/B2、libc和ISO全部通过；C3主专项在末尾真实旧GCC重定向导出检查
失败，许可检查因原样上游源码无SPDX失败。前者揭示冻结GNU CRT连B2 file_handles
都不认识，不能假称ordinary file stdio兼容：新loader对未知能力的file stdio继承
明确ENOTSUP，当前SDK标记目标继续真实共享句柄，不用path重开。对应旧工具边界
测试改为验证显式拒绝与空预创建文件，普通console GCC版本及编译仍真实验收。
旧B2未标记二进制需当前SDK重建，xypm迁移要求已写入，未降低新SDK B2 Gate。
原始失败/精确candidate SDK镜像保留build/dash_c3_failed_legacy_stdio_report.json
与build/dash_c3_candidate_c104e286/。

许可检查保留已有SPDX规则不变，新增仅对component/upstream下逐SHA锁定的原样
vendored文件验证其登记LICENSE/声明；不往原始Make源码塞新SPDX破坏源hash。


## 最终C3 Gate：passed（2026-10-26）

实现源码e729dc6511ede000a6cfaf57bf771934f8310eea（完整历史保留a455f53、6e57afd、
3079484等审查阶段），build2f7160b7d6633ee6，kernel380988B。QEMU11.1.2 TCG/
pc-i440fx-10.0/qemu64/512M/1CPU/无网络；GCC/G++16.2.0、Binutils2.47.20260726、
NASM3.02。完整source/工具/镜像/SDK/测试输入输出哈希见最终qualification与各报告。

最终22个串行验收入口全部退出0：C3主66项、exec16项、atomic7项，C2/C1及其
机制/pthread探针，进程/文件/线程/C++、CPython T3-PY、native GCC/G++、持久化、
Dash A/B0/B1/B2、libc、ISO A2和A3/A4、许可材料。新ABI拒绝旧未知CRT file stdio
和exec边界、同PID权限下降3→2、onestage EBUSY、真实fork/exec部分ENOMEM回滚、
raw legacy短写保持、小写原子与反压、1MiB捕获错误清理均有真实客体证据。

最终资源baseline=end=[129826,2,0]。普通SDK tree SHA256
`d531a24b2f679c8ae4b96fd6cb18127bb42a0798ac306152a4c90d362764e393`，线程SDK tree
`8cf47213690c2dbe95719c087cb1f84b456ddc06b9f2b7987940b00d4a747444`；后者仍不支持fork/exec。
本机冻结build/dash_c3_frozen/，公开源码回执docs/reports/dash_c3_20261026/。
SDK manifest保留构建时not_run字段，qualification按完整SHA单独给出实际资格，不
事后改输入manifest再伪绑定二进制。xos.img SHA256
`5deb880b9479ce7b155a24362fe97a7290938112244da4d41b3ebffbba1b0a1d`以实际qualification为准。

测试源最终仅修正report-only旧预期字段：ordinary console expected0与file-stdio
expected126分别命名；真实run断言此前已严格要求file-stdio=126并通过，运行行为/
输出/状态未改变。原JSON完整保留dash_c3_report.raw.json，修正副本附erratum，
不以修改结果伪造通过。源码e729为实际构建/运行版本，之后资格提交为文档与报告。
所有失败日志与精确候选SDK/镜像（含c104）保留，不删除历史失败。

不承诺：完整POSIX/GNU Make、async signals/后台/Qt/SMP、线程fork/exec、未知旧
CRT继承文件stdio、任意RPC迟到恢复、掉电匿名遗留回收、新SDK xypm白名单或无关
大型随机压力。未修改/发布正式Release，不自动合并上游。
