# XOS 当前状态

> `feature/dash-c1-c3`：C1/C2/C3三个Gate及受影响旧回归全部passed。
> 最终源码实现e729dc6，build2f7160b7d6633ee6；22个最终串行验收入口全部退出0。
> 冻结证据docs/reports/dash_c{1,2,3}_20261026/；不是完整POSIX或正式Release。
> 固定上游integration基线4c78b27，未合并上游，旧SDK的exec/file-stdio兼容边界明确拒绝。


更新时间：2026-10-26（Asia/Shanghai）。本页上方为实验分支状态，后文保留integration基线历史。

## 本分支C阶段交付

0047/0048/0049分别记录C1并发pipe、C2真实fork隔离、C3匿名HereDoc/真实exec/Make。
C1/C2各自冻结后才进入下一阶段。C3主专项66项、exec16项、atomic pipe7项，
真实GCC/G++编译/链接、自建Make与消费、CPython/线程/文件/进程/持久化、旧Dash
与ISO/许可回归均passed，最终资源[129826,2,0]。SDK普通/线程profile与不可用能力
见shell_subset.md、e04_loader_sdk.md和最终qualification.json，不混用旧静态CRT。

后台/async POSIX信号、SMP、Qt、线程fork/exec、xypm新SDK登记仍不支持/未运行。
审查入口：UPSTREAM_DASH_C1_C3_REVIEW.md。未触碰日常盘、旧Release或localpilot。

## integration基线历史状态（4c78b27）

主线已合并线程 PR（基线 `d89d1a3`），并在其上完成 dash B2、file-backed ISO
A2–A4、CPython T3-PY gate 和 xypm P1。最近一次完整 gate 的 build 为
`911184be3f3c99f6`；当前源码重建为 `f25009cdbb27c857`（未重跑全量），
基础镜像 SHA256
`d9b81936924e729d2cf059d936b2406828a6785c151246603ed77ec9b2c5121d`。
最新入口看[项目总览](project_overview.md)和[下一次 release 准备](releases/next_release.md)。

已通过：启动/文件/进程、E08 受限工具链、dash B0–B2、xypm P0/P1 与双 Shell
10/10、CPython T3-PY 5/5、ISO A2–A4 旧 build 报告。未完成：**ISO 容量扩展**
（本组不负责）、CPython T3-QT/SMP、完整 POSIX/pipes、xypm P2/P3、Qt/UEFI、
旧全量回归/压力。不要把 A2–A4 的“kernel 从 ISO 文件加载”写成“容量已突破”。

以 xos_plan.md v0.10 正文、后续决定和本页状态为准。下划线命名、轻松开发、过程落盘；
固件/ISA/平台/通用内核分层。localpilot/ 独立，不进入 XOS 构建、扫描或清理。
顺序 E05 → E07 → E06 已完成；E08 受限功能 gate 收口。新一组重新登记范围，
不得并发构建/清理 build/，GNU 专属 cache 构建使用独立 SDK 快照。

Git origin 为 Xiao-John/XylophoneOS。0023 发布使用本机凭据且不落盘；原日常
work_disk.img 保留，测试使用临时专用盘。

## 0045 完成：总览、文档清理与 release 准备

删除 `.DS_Store` 和 tests/scripts 的 `__pycache__`；新增
[项目总览](project_overview.md)、[下一次 release 清单](releases/next_release.md)
和本记录。更新文档索引，区分入口、work_log 证据、冻结报告和压缩发行材料。
未删除 work_log、线程冻结报告或发行附件；清掉旧 release 目录中两份逐字节
重复的源码压缩包，canonical 保留在 `sources/`。未构建/打包新 release。
发现 install ISO 报告仍绑定旧 build `26eb667dd8318997`，且 ISO 容量仍受
512 KiB kernel/4 MiB 页表/1 MiB payload 限制，已写入 release 阻塞项。
详见[work_log/0045_release_prep.md](work_log/0045_release_prep.md)。

## 0043 完成：CPython T3-PY 客体 gate

T3-PY 首次 4/5，原因是 XOS pipe 读为显式 `EAGAIN`，不能作为阻塞 I/O 证据。
gate 改用真实 files 服务 `read(4096)`，并要求后台线程跨多个 I/O 窗口推进；
`tests/cpython_t3_py_smoke.py` 5/5、资源 `[129833,2,0]`，fingerprint
`cebe2527e705a185b6b9`。XOS pipe 仍非阻塞；T3-QT/SMP/完整 POSIX 未验。
详见[work_log/0043_cpython_t3_py.md](work_log/0043_cpython_t3_py.md)。

## 0044 完成：xypm 定名与 P1 双 Shell 验收

包管理器正式定名 **xypm**，命令/脚本/模块/原生程序/包ID/数据库目录统一改名，
不保留 xpm/xpkg 可执行别名；`.xpk` 与 v1 容器/schema 不变。P1 交付宿主候选盘
install/upgrade/remove、归属/依赖校验和客体只读 list/info；客体写入事务留给
P2，仓库/签名留给 P3。宿主导出临时文件重名问题已修：会话 uuid 前缀 + 递增
serial + 排他创建。

证据：`build/package_p1/xypm_rename_p0_report.json` 16/16、
`xypm_rename_host_report.json` 12/12、
`xypm_acceptance/guest_report.json` 10/10（双 Shell 查询/退出码、B2 重定向、
升级/移除后重启、用户输出保留）。系统 build `911184be3f3c99f6`，资源
`[129833,2,0]`，xypm 包 SHA256 `86a7f72f…`，final image `dfa3881d…`。
未运行：P2 客体写入事务、P3 签名仓库、线程 SDK 登记、旧压力。详见
[work_log/0044_xypm_p1.md](work_log/0044_xypm_p1.md)。

## 0041完成：多线程PR本地整合确认

已fetch并快进到d89d1a3；本地B2/ISO/其他未提交改动有恢复快照，4文件冲突已
逐处整合，无unmerged entries。线程38–52保持远端定义，本地ISO payload改53；
B2顺序动作在私有FD快照执行，Client新操作加session锁，嵌套取消适配线程模型。
隔离构建660723db5e2b005e通过，新整合7组客体通过，前6组资源[129833,2,0]恢复；
第7组确认ISO sys53安装/运行dash。报告build/thread_merge_check/merge_report.json、
merge_receipt.json，详细范围/失败修复见work_log/0041_threading_local_merge.md。
本组占用解除，B2仍按用户要求暂停；后续包管理线改名为xypm继续。整合修正仍在工作树，未提交
或push，不自动恢复stash覆盖它们。不执行用户计划中的ISO回滚或新Release。
未重跑PR全T2资格/旧压力，未把其旧回执改绑本地SDK；cpy仍由另一侧推进。

## 0039 xpm P1准备（旧名；现名 xypm，由0044续接）

用户当时定名xpm并要求同步dash/xsh能力边界；0044因撞名改为xypm。主端占用
原xpm脚本、新增宿主
FatFs会话后端、build_xpm.py、只读用户态xpm程序及tests/package_p1_*、自有说明/
状态；P0 xpkg入口保留兼容。只读复用冻结SDK/隔离镜像，不修改0037的ABI/files/
loader/libc/dash端口、0038或游戏源码。专用build/package_p1与cache；双Shell原计划
用固定已验dash B1准备同一外部xpm验收，不借用随后0042的B2回执。

## 0042完成：dash B2

0037的文件打开实例转交、共享偏移、spawn顺序文件动作、dash重定向和嵌套前台
取消已在0041线程整合后正式验收。最终系统build `911184be3f3c99f6`，xos.img
SHA256 `d9b81936924e729d2cf059d936b2406828a6785c151246603ed77ec9b2c5121d`；
dash SHA256 `a730086417e2d3f7204824c9dd1f6ac25cac61e3b0fd59747315fcba72e11646`。
B2专项6项、B0/B1回归7项、进程/SDK回归13项和许可材料检查均通过，客体资源
回到`[129833,2,0]`。证据在build/dash_b2_acceptance_report.json、
build/dash_b_acceptance_report.json、build/process_smoke_report.json、
build/license_report.json和work_log/0042_dash_b2.md。C阶段管道、子Shell、后台、
命令替换与here-document仍未实现；本组未提交或推送，`localpilot/`保持隔离。

## 0038 完成：CPython PY1

PY1生成固定560文件的stage及逐文件路径/大小/SHA256清单；客体6/6通过：精确
argv、cwd `/`、继承PATH、脚本目录优先import且无宿主路径，选定标准库实际操作，
二进制字节原样读取，以及缺模块/语法错误/未捕获异常退出1。解释器fingerprint
`ad85d8438b4101d66483`，冻结SDK `2c3876e640840ff5`；测试复用系统build
`3d7665a665df9443`和隔离临时盘，报告`build/cpython_py1_report.json`。未修改或
重建内核、文件ABI、files、loader、libc、dash/sbase，未清理共享build或操作日常
工作盘。全标准库、REPL/input、JSON存档和重启持久性仍未验，下一步PY2。详见
[work_log/0038_cpython_py1.md](work_log/0038_cpython_py1.md)。本组无剩余编辑占用。

## 0036：当前基线提交/推送交接

用户要求立即推送main供朋友多线程PR，不等待Open Adventure。本次收口已完成的
Shell/UTF-8/CPython PY0/包管理P0与契约文档；游戏进行中源码src/ports/adventure/
保留本地，不提交或删除。朋友按threading_contract.md从T0开工，syscall已至37；
主端继续包管理P1，不并行改线程代码。核心源码摘要与3d7665a665df9443回执一致；
没有重建或重跑旧测试。补齐CPython原许可证与登记，不改发行标签/附件。
范围与接手说明见work_log/0036_thread_pr_baseline.md；Git提交/远端ref定位实际快照。

## 0035完成：包管理P0实现

用户将多线程实施交朋友、通过PR接收；本线优先包管理，不占内核/ABI/libc源码。
宿主scripts/xos_app.py已支持独立项目init/build/check/pack，scripts/xpkg.py支持
pack/inspect/verify；共享xpkg_format.py严格校验v1普通文件ustar/JSON、路径/哈希/
受限ELF和声明profile；config/package/冻结schema及已验发行SDK快照profile。
只接受明确登记的完整单线程SDK，不把任意同ISA/新线程库冒认为兼容。
宿主16组通过，真实仓库外C/C++项目构建与重复打包；2项包payload客体退出0，
每项资源[130342,2,0]恢复。用冻结系统2c3876e640840ff5和全新测试盘，通过已有
文件桥传输；不是通用安装器验收，未重建系统或操作日常盘/发行附件。
报告build/package_p0/host_report.json、guest_report.json、final_receipt.json；关键
哈希见work_log/0035_package_p0.md。主计划v0.9及开发入口已同步。
P0受限完成，P1安装/归属数据库、P2客体xpkg/P3仓库仍not_run；下一步P1独立
候选盘新安装与源盘保护。未改Open Adventure/CPython/UTF-8源码、未跑旧压力。
本组结束，无剩余编辑占用；未提交/推送或派出agent，线程PR尚待接收。

## 0040 完成：ISO 安装介质 A3/A4

dash 作为 ISO payload：loader 读 `DASH.ELF`，kernel 复制到 1 MiB 静态区，
新 `sys_boot_payload` 交给 supervisor，`file_ui` 自动安装到 `/usr/bin/dash`
（已有文件不覆盖）。`build_install_iso.py` 生成含 `KERNEL.BIN`/`DASH.ELF`/
`MANIFEST.TXT` 的 install ISO 和宿主 manifest；`make run` 默认使用它，
`make run_file`/`make run_iso` 保留无 dash/嵌入 kernel 版本。build
`26eb667dd8318997`，install ISO SHA256 `c29db082…`；
`tests/iso_dash_install.py` 4/4、A2 回归 2/2。限制：payload 1 MiB、kernel
仍受 512 KiB 构建上限/4 MiB 页表、无签名/交互分区。详见
[work_log/0040_iso_install.md](work_log/0040_iso_install.md)。

## 0039 完成：ISO 容量 A2（文件加载 kernel）

loader 从 ISO 读 `KERNEL.BIN` 并直接装入 1 MiB；boot image 只有 boot sector +
loader。修复 `rep insw` 后重复 `add edi,2048` 的扇区间空洞后，内核进入并到
`xsh>`。最终 build `26eb667dd8318997`，`xos-install.iso` SHA256 `fc3bad2c…`；
`tests/iso_file_kernel_smoke.py` 2/2 通过。后续 A3/A4 见 0040；`make run_file`
保留无 dash 的 file-backed ISO，`make run_iso` 保留嵌入 kernel 的旧 ISO。
kernel 文件仍受 512 KiB 构建配置和前 4 MiB 页表限制。详见
[work_log/0039_a2_attempt.md](work_log/0039_a2_attempt.md)。

## 0038 完成：ISO 容量路线 A1（ISO9660 文件）

独立探针通过 ATAPI 逐扇区读 PVD 和根目录，按 extent/size 读出
`KERNEL.BIN`/`DASH.ELF`，多扇区文件（2100/5000 字节）校验通过；报告
`build/cd_iso9660_report.json`，串口 `A1 ok KERNEL=2100 DASH=5000`。限制为
单层根目录、`;1` 名称、单 extent、<64 KiB；尚未把 kernel 装到 1 MiB 以上。
现有 `xos.iso`/`make run` 路径未改。计划见[iso_install_plan.md](iso_install_plan.md)，
过程见[work_log/0038_iso9660_a1.md](work_log/0038_iso9660_a1.md)。

## 0037 完成：ISO 容量路线 A0（ATAPI PVD）

在独立探针中验证 ATAPI PIO 可读 CD 的 PVD（LBA 16），串口输出
`CDTEST ok: CD001`；报告 `build/cd_atapi_report.json`。no-emulation CD 的 BIOS
`INT 13h AH=42h` 实测返回 `ah=01`，因此后续 loader 走 ATAPI 而非 BIOS 读盘。
现有 `xos.iso`/`make run` 路径未改；A1 才是 ISO9660 文件与 kernel 读取。
计划与 A0–A4 见[iso_install_plan.md](iso_install_plan.md)，过程见
[work_log/0037_cd_atapi_a0.md](work_log/0037_cd_atapi_a0.md)。

## 0036 完成：El Torito ISO 启动

`make run` 默认改为 `build/xos.iso`（El Torito no-emulation），boot sector、
loader、kernel 一起装进 boot image，不再读软盘；`make run_floppy` 保留旧路径。
build `2b5f6ecc87ed6d8f`，ISO SHA256 `209367f7…`，`tests/iso_boot_smoke.py`
2/2 通过；预装 dash 的盘配 ISO 也可 `dash -i`。仍受真实模式 640 KiB 边界，
不是 UEFI。过程见[work_log/0036_iso_boot.md](work_log/0036_iso_boot.md)。

## 0035 完成：新工作盘预装 dash

dash 仍不能进入 128 KiB 启动模块，改为预装到工作盘：`make dash` 用当前
`build/sdk` 构建，`make disk` 新建盘后自动导入 `/usr/bin/dash`；已有盘不自动
修改，可用 `scripts/install_dash.py` 补装。上游 dash 源码包固化在
`src/ports/dash/upstream/`，离线可构建。验证：build `38c014699e36553f`，
`dash -i`、`echo`、`exit` 通过，`build/dash_preinstall_report.json` 4/4。
发行打包脚本也改为对新发行盘预装；冻结的 0.0.1-1024 未重打包。
过程见[work_log/0035_dash_preinstall.md](work_log/0035_dash_preinstall.md)。

## 0034 完成：Open Adventure 在 XOS 内构建

冻结 Open Adventure 1.12（BSD-2，包 SHA256 `b6db9554…`），在 port 内实现最小
PyYAML 子集、readline 适配和 `build.sh`；客体由 dash 执行脚本，用既有
`/usr/bin/python3` 生成 `dungeon.c/h`，再由原生 GCC 链接 `/out/advent`。
生成数据与宿主 PyYAML 6.0.3 参考逐字节一致；中文欢迎语、起点、得分/等级和
灯/钥匙/宝箱/金币文本通过客体检查，英文命令仍正常。报告
`build/adventure_report.json` 4/4，build `3d7665a665df9443`。仅部分翻译；
存档/读档、脚本输入、完整流程和中文排版未验。计划见
[adventure_port_plan.md](adventure_port_plan.md)，过程见
[work_log/0034_adventure.md](work_log/0034_adventure.md)。本组无剩余编辑占用；
下一步扩充翻译并补存档/脚本 gate。

## 0033 完成：UTF-8文本通道 U0/U1

Xsh与dash的控制台行编辑已接受UTF-8字节，按码点退格、按显示宽度擦除；非法UTF-8
整行拒绝，合法字节原样传给argv。共享实现`xos::text`（解码/校验/宽度/erase_last），
未改文件服务、locale、内核控制台或进程ABI。系统build`3d7665a665df9443`，镜像
SHA256 `74b07888…`。主目标通过：客体原生G++编译运行`UNICODE_example1.cpp`，
逐字节输出德/中两行；Xsh 6/6、dash 4/4客体检查通过。dash空闲读的
EWOULDBLOCK刷屏已修为yield重试；dash用当前`build/sdk`重建。

明确限制：UTF-8文件名/目录仍受U2的ASCII路径限制（`cannot read program`）；
VGA不渲染UTF-8；无UTF-8 locale/字符级glob；无客体键盘/输入法。未做语言包管理器。
计划见[utf8_text_plan.md](utf8_text_plan.md)，过程与哈希见
[work_log/0033_utf8_text.md](work_log/0033_utf8_text.md)。本组无剩余编辑占用；
下一步U2路径，L0只读数据包+Unicode工具可选，N1输入法另立。

## 0032完成：包管理与独立第三方开发规划

方案见[package_management.md](package_management.md)，独立SDK项目→P0开发/包
契约→P1宿主候选盘离线安装→P2客体事务/恢复→P3仓库。xos_app/xpkg与包格式
均待实施，未建立schema/CLI或包数据库。C16只确认独立开发/包管理方向，P07
记录待核验工程方案；主计划v0.8、决策/索引已同步。
重写[开发入口](friend_user_program_quickstart.md)：普通main、发行SDK compile.py、
现有离线非覆盖导入、原生GCC/G++后exec-file，不再要求改系统源码/重建镜像。
已核对0030 PY0与0033 UTF-8文本通道结果，Open Adventure由用户移植线负责；
文本UTF-8不推导路径U2。首包样本hello/CPython/Open Adventure，构建/运行依赖
分开。线程T0–T2仍优先。本组仅文档，无源码/构建/安装/客体或旧压力重跑；
记录work_log/0032_package_management.md。规划结束，无剩余编辑占用。

## 0031完成：公共线程契约与计划

用户确认E13-T提前，契约见[threading_contract.md](threading_contract.md) v1。
1:1内核线程/单核抢占；T0进程线程分离/生命周期、T1比较等待/单调时间、T2真实
pthread与线程安全newlib/C++ SDK、T3-PY/T3-QT各自接入。0028已交付，下一组可
领取T0；0030继续依赖探针，T2后真实Python线程前移，不等PY3其余生态功能。
主计划v0.7/C15、决策、CPython计划/SDK计划引用/索引已同步。所有线程实现与
gate均not_run，仅定语义/验收；数值ABI/布局由T0同步头/SDK冻结。无源码修改、
构建/客体/压力，也未修改0030源码或旧发行。详见work_log/0031_threading_contract.md。
本组文档完成，无剩余编辑占用，尚未启动线程实现或派出代理。

## 0030 完成：CPython PY0a/PY0b

接手意外暂停的移植后，PY0a/PY0b 已通过。冻结 CPython 3.14.9 与发布 SDK
`2c3876e640840ff5`；构建 fingerprint `ad85d8438b4101d66483`，静态解释器
`target_build/python.exe`（unstrip SHA256 `bc7aeca3…`，strip 后 `71839cb7…`，
7928480 字节），装入 `/usr/bin/python3` 与 `/usr/lib/python3.14/`。客体报告
`build/cpython_py0b_report.json` 7/7：`-c` 算术、脚本、Unicode、未捕获异常
退出 1、GC、同目录 import、重复启动；运行镜像 build `498ad82e530fbf23`，
SHA256 `66a98859…`。114 模块中 71 静态内建、0 共享、25 n/a、9 禁用、9 缺失。

诚实限制：无熵服务，bootstrap 固定 hash seed 0（非安全随机）；`time.sleep()`
自旋 PIT tick；无墙钟/CPU 时间、fork/exec/select/动态加载/线程；REPL 与
input/PY1 路径规则尚未验；128 KiB 用户栈要求 `-O2`。未修改 libc/内核/loader、
dash/sbase 或发布镜像，未并发运行共享构建；未重跑旧压力。证据与逐项修复见
[work_log/0030_cpython_py0.md](work_log/0030_cpython_py0.md)，构建/测试入口见
`src/ports/cpython/README.md`。本组无剩余编辑占用；下一步 PY1 脚本/import，
再 PY2 REPL/JSON 存档，熵/墙钟与 T3-PY 等公共底座另开 gate。

## 0029完成：CPython移植规划

朋友投票优先CPython，用户要求先规划，实施仍交专门用户态agent。方案见
[cpython_port_plan.md](cpython_port_plan.md)：建议3.14维护分支，先PY0a冻结源码/SDK
及依赖探针，再PY0b静态单线程核心、PY1脚本/import、PY2传统REPL与文件存档；
之后可收一次PY4分发，PY3扩展按实际底座逐项推进。线程内部锁/TSS、时钟/熵、
启动编码、输入和小栈为重点，不全球伪造pthread或POSIX。不要求fork/dash先完成。
本轮只交设计，所有CPython构建/客体gate未运行，候选版本尚未锁定；未修改0028
代码或运行共享构建/压力，未改计划正文C决策。记录work_log/0029_cpython_port_plan.md。
规划结束，无剩余编辑占用；下位agent先拿冻结SDK并重新登记范围。

## 0028完成：dash B0+B1

B0新增最大3层的显式构造权委派；非supervisor只能给直接building子任务
更小深度。旧grant_spawn仍是一层直接构造权。Xsh仅对裸dash启动配置深度2，
dash的用户态固定profile仅对GCC/G++ driver委派1层；内核不识别工具名或路径。
未获委派的exec-driver dash启动GCC被明确EPERM拒绝、退126且无目标文件。

B1放行case、函数、dot source和已有参数展开；引入锁定sbase commit
c546c3a5724c81cee9a11d816a38ccdf17472129的cat/cp/mkdir/mv/rm窄子集。最终隔离构建
f3fdb780732801ab，xos.img SHA256 b91905f4ec723326a7863c0a6c6aee4d956c24b057c337214ae0116f455b6d3b；
dash SHA256 195f49af2471bc5d3b39bea68ebc056ee81416cba0700d0510a87cdbd5a5cfdb。
B0/B1 7项客体gate通过：真实GCC→cc1/as/ld、G++→cc1plus/as/ld，故意编译失败后
cp修改源码、重译并执行C/C++，工具文件副作用和拒绝路径；各组资源回到
[130336,2,0]。dash A 16项回归与许可材料检查通过；无管道/重定向/子Shell/
后台/exec替换，B2/C仍未开始。证据build/dash_b_final2/dash_b_acceptance_report.json、
.cache/xos_seed/dash/39f57f408a4362fda92e/shell_smoke_report.json与work_log/0028_dash_b0_b1.md。
本组完成，无编辑占用；发行附件、日常工作盘和localpilot未改。

## 0027完成：Xsh交互与可执行查找优化

用户追加可执行文件设计优化并授权子agent。主agent占用supervisor.cpp、整合/文档和
build/xsh_ui串行构建；kernel_trace子agent独占tasks.cpp/process_abi.hpp的日志开关；
execution子agent独占新增execution.hpp、loader候选检查/结构化启动诊断及user_build.py
的loader对象登记；ui_cases子agent独占tests/xsh_ui_smoke.py与新夹具。接口先固定后
并行编辑，不覆盖对方文件。PATH/ELF/错误解释都在用户态，driver授权语义本组不改。
不动发行附件、localpilot或他人文档整理；旧sup>测试适配在定向runner中明确处理。
统一隔离构建b508acc417e218b3，build/xsh_ui/xos.img SHA256
2371b0118ea1499450f49d4801e87238073eec86a45679fad2f25714e087499b。
新UI/执行11组、dash A16项客体通过，资源基线[130336,2,0]逐组恢复。
欢迎/提示改xsh>，默认成功简洁、trace on可看详情；type显示命令来源。PATH按ELF
检查跳过无效候选，显式路径不fallback，资源/读取错误停止搜索；结构化装载错误
与sys36仅supervisor诊断开关见xsh.md。ABI/脚本/授权仍有明确范围。
新增候选与装载两文件AArch64仅编译通过，许可材料检查通过；未重跑旧全量/压力。
证据work_log/0027_xsh_execution_ui.md；后续dash计划dash_port_plan.md，B0/B1优先。
本组完成，三个子agent均交付，无编辑占用；共享发布镜像/日常盘未变。

## 0026完成：确认Xshell exd与PATH

用户新增的exd别名与固定PATH=/usr/bin:/bin:/已定向客体验证，系统498ad82e530fbf23。
exd dash脚本可经继承PATH再次启动hello；裸dash、原exec-driver与显式路径均退出0，
四项资源回到[130342,2,0]。见work_log/0026_xshell_alias_confirmation.md；没有修改
对方实现。0025所述并发PATH修改现由0026补验，dash仍为可选程序，无编辑占用。

## 0025完成：可选dash A与E09发行交付收口

用户授权开始dash A。主agent占用src/ports/dash/、scripts/build_dash.py、
tests/shell_smoke.py、docs/shell_subset.md及本页/工作记录/计划。隔离构建使用
.cache/xos_seed/dash/和发行冻结SDK，测试用独立盘。cd /暴露files根路径被尾斜杠
检查拒绝，主端增加files.cpp这一行修复与build/dash_system隔离系统重建；不改发布镜像。
E09发行交付完成；朋友独立试用和备份恢复/升级验收记录仍待补，不假报已测。
用户确认Xshell/xsh保留原生入口与交互定义权；dash是/usr/bin/dash可选程序，
不替换默认Shell，不自动安装/bin/sh。A的16项客体验证通过，退出回到Xshell。
ELF SHA256 97dd273e34924203bad691df02b3f4f13e3fd448571c84d2065335c05fb7072e，
系统64fcf112f8efc899含根路径修复。报告shell_subset.md、work_log/0025_dash_a.md。
同时发现其他任务在整理历史文档和改supervisor PATH；均未覆盖。本次镜像使用
发布版supervisor，后来的PATH修改未验，不声称最新工作区整体已验收。B/C尚未开始。
本组无剩余编辑占用；下一步可按B继续，或独立改善xsh交互。

## 0024完成：Shell移植勘查

主agent只占用docs/shell_port_scout.md、work_log/0024_shell_port_scout.md和本页，
下载/配置/编译探测限定.cache/xos_seed/shell_scout/，不构建主系统或运行旧压力。
比较dash与BusyBox hush的真实进程/描述符依赖，确定最短落地路线；不把源码分析
或宿主编译当成XOS客体运行。压力从端文件和发行标签/附件不修改。
建议dash 0.5.13.5 + 受限posix_spawn执行后端，先简单命令/脚本，再描述符与
原生编译，最后管道/隔离执行。dash目标configure通过，make部分生成14对象后
失败；尚无完整Shell ELF或客体运行。hush NOMMU仍需vfork且有libbb/组合许可成本。
报告shell_port_scout.md、工作记录0024；本组已结束，无剩余占用。路线是建议，
尚未修改主计划或标记Shell已实现；下一步可直接按报告A批次实施。

## 0023完成：首个正式发布

用户授权今天发布GitHub xiao-john/xylophoneos正式Release，版本0.0.1-1024。
主端占用scripts/package_release.py、发布文档/README、独立build/releases/、Git提交/
标签/Release上传；压力从端仍占用其测试/报告，不覆盖或清理其build路径，不并发
make build。发布先复制已验证镜像/SDK到独立目录，打包验证只操作发布副本。
GNU对应源码、许可、安装工具链映射/校验与启动说明随包提供；不得读取/纳入localpilot。
2026-10-24 23:53:21 CST正式公开Release（draft=false/prerelease=false），8项附件上传并核对远端摘要。
标签v0.0.1-1024绑定0e541badf27a23e2928881279cff5f165de8b4c9；内核build仍为2c3876e640840ff5。
SDK C/C++宿主编译和四项新包客体验证通过，见work_log/0023_first_release.md。
发行回执releases/release_0_0_1_1024.json；压力从端的测试/报告未纳入本组提交，仍由其维护。
发布工作已结束；后续修复使用新版本，不移动此标签或静默替换发行镜像。

## 0022完成：原生G++与E08功能闭环

接收A/B后，六项早期ABI客体通过；E08-5原生G++设施4组/14命令通过，
6b7d5cfc3612fdf4，资源[130342,2,0]。实际修复TLS回退重复定义和g++ lrealpath漏返回，
原始输入不覆盖，派生入口/安装命令见e08.md与e08.md。
当前最终系统2c3876e640840ff5，xos.img SHA256
1c2cfa90d65b9a9585ac3d5cef32c8376b1806e65f7502321912b2e15b54454c。
E08-6 C++编辑→重编→运行→sync→重启通过4项/18命令，结合0021已通过的C增量，
主端判定E08受限功能验收通过，O11/O12/O13在固定静态配置通过。单语言原报告
仍标partial，综合报告e08.md、build/e08_acceptance_report.json
分别绑定测试版本；没有重跑C/旧CRT/历史压力，也不把旧证据归到最终镜像同一次测试。
最终系统与native gate相比仅更新目标库许可登记，实际CRT/库/头与SDK v5一致。
目标库与修复G++分别在.cache/xos_seed/gcc/relinks/target_runtime_v5_receipt/、
gxx_lrealpath_v5/；组合白名单build/cpp_bundle/。不要使用原始B g++（仍含已暴露bug）。
原生G++产物848056字节；最终编辑重启C++产物791368字节，完整hash见0022。
collect2、动态链接/TLS、线程、完整POSIX/标准库、自举不在范围；真实内存/磁盘
高水位和后续压力仍由专人负责。327项源码hash与manifest一致，7份许可材料检查通过。
本组结束，没有剩余代理占用或QEMU。下一步按计划E09交付/朋友试用，尚未开始；
Qt、系统重建、自举不因本组通过自动开工。下面0021/旧阶段保留作历史。

## 0021历史：E08-5与E08-6准备

用户授权开始E08-5，争取2026-10-24晚进入E08验收。主端负责libc/ABI/SDK、C++
安装整合/正式gate、共享文档与build/串行构建/QEMU。从端任务已写
e08.md，外部从端待用户转交/启动，不能误认为已经运行；独占
GNU构建脚本/ports/gcc及新e08_5私有cache，优先分批交target运行库，再交g++/cc1plus。
本轮两位Luna均已交付冻结，主端当前持有共享文件和build/，没有其他编辑占用。
主端新运行基底f40c9a254b5433d7已构建，TLS main-return/显式exit两条客体路径通过，
资源[130342,2,0]；SDK v5冻结到.cache/xos_seed/sdk_snapshots/3a302b5cd7e1cdab0f594b0d16d7ca92b753fec7b2efcc6347b01e5a69542edd，manifest SHA256同名。
新增__cxa_thread_atexit/正常exit TLS先于global析构，不改内核ABI；旧快照保留。
C++安装/profile合同5例、v5 target sysroot readonly预检、许可材料核对通过。
E08-5仍not_run；E08-6提前验证的C部分已通过4项/18命令（82ffcecab8ccbcce），
报告build/e08_6_c_report.json；旧测试镜像/manifest已保存，不因新构建丢失绑定。
完整记录e08.md。等待从端分批交真实target库/G++后继续
独立ABI→原生G++设施→C++编辑/重启增量。C++未验，不标E08-6/整体通过。
不重跑已完成C gate/旧压力，后续压力由专人负责。

## 0018–0019历史：E08-4/5分工

0018已写好主agent（含Luna）与另一协作agent的执行prompt，入口
[e08.md](e08.md)。主agent负责ABI/运行基底/集成/验收，
协作者负责GCC/G++构建和依赖闭包；build/归主agent串行使用。
用户已启动从端；主agent现在启动实施。主agent独占内核/loader/ABI、构建集成、
共享文档和build/；luna_runtime负责指定libc分析/实现，luna_cases负责新增测试；
从端独占GCC构建/ports/gcc与私有cache；Luna本组任务已交付，暂无其活跃编辑占用。
详细分工见协调页。最新0020已接收并验收C Seed，Luna均交付且无剩余编辑占用；E08-5仍not_run。
主端0019已通过CRT/静态TLS/exec-access/真实libgcc回溯/拒绝路径8组客体功能
（9830f208cc2095a4）及12例TLS解析检查；通用loader两文件AArch64仅编译通过，
SDK v2已冻结到 .cache/xos_seed/sdk_snapshots/f5c74adecb9515878fdbce14a56062cb0567772ae183edecf2a455d15a1f9f74，
供从端构建使用；不包含libstdc++/libsupc++，不能当GCC/C++阶段完成。
从端<algorithm>阻塞已回复：由从端先构建真实host静态标准库闭包，继续指令在
[主端回复](e08.md)，不等待主端另交预构建STL。

## 0020已完成：C Seed集成与验收

E08-4受限功能gate通过，构建82ffcecab8ccbcce，xos.img SHA256
bd5dd6d7342b42ce5904f0937675c3285f9058fa93d0568792b63e3d31530a8d。
4组/15命令：真实GCC/cc1/as/ld多文件归档链接与执行、libgcc128位辅助函数、
错误路径、源码逐字节保护；每条资源恢复[130342,2,0]。完整证据和接续命令见
[e08.md](e08.md)。
修复lrealpath漏返回值、O_NOCTTY拒绝、as安装名和8-open链接容量缺口；
文件消息布局不变，每会话16打开/全局32锁。SDK v4冻结为
.cache/xos_seed/sdk_snapshots/1ba7c52c568725cac63c4a9e603aabd61f30e00db430ca0e5afb4fcfee956490，
manifest SHA256同名。派生Seed为.cache/xos_seed/gcc/relinks/open_capacity_fix/seed_manifest.json；
不要使用从端原始gcc二进制（仍含已暴露bug），原始manifest只作来源证据。
预检18例、diagnostics9例通过，7份许可材料与登记GNU组件哈希核对通过；
C++ ABI runner已准备，拒绝host运行库的guard通过，真正目标库/客体ABI仍not_ready。
当前没有代理剩余编辑占用，不重跑旧CRT/TLS/压力测试；压力仍由专人负责。
collect2未重链接/未验收，当前profile直接使用真正GNU ld，不扩大构造权。

## 本组修复与测试边界

0017 已完成：主 agent 仅修复 S2 暴露的 libc 初始文件偏移错误；普通 open 从0、
O_APPEND 从EOF。文件位置探针及原现场 archive final-link/执行/strip 定向回归通过。
没有剩余编辑占用；不重跑 S0/S1/S3/S4 或 make smoke，后续压力测试由专人负责。

当前定向验证构建 b1ded17e673ccffc，xos.img SHA256
baa37982b222a59a836def90c4586be70743ea88e26ac9b70843c8fa5f97507d。
新 Seed 为 a983a603cb4132f7ff02bc3471978e5099e28dad7a60f8a33658358938f14479，
manifest SHA256 4986571a249ba23a814454848837eaebb0791dbb5dc6273c563df1c141dc4193。
运行时已静态链接进新工具，旧 Seed 仍含 bug，不应与修复版本混用。
对应 SDK 快照 f187691498b56720feb7ee118ad6cd70b2808cd4145ad7d4ea3d640ee51a1a93。
证据 build/archive_link_regression_report.json、file_position_regression_report.json、
e08.md；下面5276ff16全量结果仍属于历史版本，
不冒称本次全量已复验。S2 原压力失败报告保留，定向修复不将整份压力测试改成全绿。

## 当前已实现

- 0001–0006：实模式练习、BIOS/x86-64 内核、异常/页管理、ring3、抢占、IPC、监督回收。
- 0007：E04 用户态 ELF 装载、SDK、argv/stdio、启动/等待/退出/故障结果与回滚。
- 0008：E05 文件/编辑器；0009：E07 ATA PIO、用户态 FatFs、同步和正常重启持久化。
- 0010：E06 newlib 4.6.0.20260123、libc_hello、用户任务 FXSAVE/FXRSTOR。
- 0011：E08-0/pre1 资源审计与设计；0012：E08-1 存储/会话/流式装载 gate。
- 0013：E08-2进程/libc/stdio/动态堆；0014：许可管理；0015：真正GNU binutils Seed。

当前机制：

- QEMU pc-i440fx-10.0、qemu64、TCG、单核、512 MiB RAM，无网络；只读软盘启动，
  独立 IDE 工作盘。物理页管理上限 512 MiB；1 GiB 用户窗口、65536 页/任务
  （256 MiB，含栈）、8 任务、16 未收集完成记录。分配提示与页表回收经过压力验证。
- 新盘默认 2 GiB FAT32 稀疏镜像，显式 make disk 创建；已有 16 MiB FAT16 可继续用，
  不自动格式化/迁移。512 MiB 与 2 GiB FAT32 均已运行验证。工作盘独立于 build/。
- ATA PIO 仍在 kernel/platform/pc：LBA28、每次最多 8 扇区、有界超时、FLUSH；
  block ABI 只允许 files 服务。FatFs/路径/文件内容在 ring3。
- 文件 ABI v2：4096 字节消息、255 字节以内 ASCII 路径、LFN/目录、根相对路径，
  无 cwd/dot 路径/Unicode。文件不再限制为 4×24 KiB；大小 u32，保守 FAT32 上界
  0xfffffffe，实际受格式与可用磁盘空间约束。每会话 16 打开、全局 32 个 FatFs 对象锁（0020调整）。
- 内核为普通子程序分配独立请求/响应端点，绑定真实发送/接收 PID；files 用专属
  sys_file_session 枚举任务槽。端点 token 在一次启动内单调不复用；退出/abort
  清理端点，files 清理旧 PID 的打开实例和未提交保存。任务不继承 builder/块设备权限。
- 保存 staging 直接在磁盘，顺序 chunk、commit/abort；全局一笔保存，其他活客户端
  返回 busy，不能抢走 staging。延续 temp/journal/backup 恢复；正常同步重启已验证，
  不承诺任意掉电事务原子性。hello.elf 只在缺失时注入。
- ELF 校验在用户态，文件装载持有读锁并按段/页读取，无整文件 RAM 缓冲；零填 BSS，
  W^X/范围/入口/页预算检查，失败关闭/abort。只读启动模块仍有 128 KiB 限制，
  工作盘 ELF 不受该限制。SDK 的 AArch64 编译检查不代表第二 ISA 移植。
- sup> 提供 ls [path]/cat/stat/rm/edit/filetest/sync/exec-file/exec-driver/spawn-file/mkdir/mv；
  既有 exec/spawn/wait/kill/stats/primtest/elftest 保留。files/supervisor 是受保护
  bootstrap 服务，kill 拒绝；普通程序可被 kill 或前台 Escape 取消并 wait。
- 编辑器仍 8 KiB，正文原样保存；终端按空格分词，无引号。argv 最多64项/每项
  255字节，argv/env/cwd共享4页startup；32页可用栈另加guard。
  cat分块输出；SDK路径可有空格，终端暂不能输入带空格的路径。
- E08-2 newlib适配已连接真实文件/目录/临时文件/errno、动态sbrk堆、受限
  posix_spawn/waitpid/stdio/pipe。exec-driver显式授权，不继承给孙任务；
  普通程序不能创建子工具。最终5组runtime检查及完整集成回归通过。
  限制见e08.md；不是完整POSIX，无fork/mmap/墙钟/符号链接/权限位。
- stat/fstat返回真实SFN目录项映射身份，root inode=1、其余16位编号不复用，
  每次服务生命最多65534个非root身份，耗尽失败；rename/保存保持身份。
- GNU Binutils 2.47的as/ld/ar/ranlib/strip为工作盘XOS可执行Seed，真正客体产出
  目标文件/静态库/ELF，strip后重启可执行。另4个工具仅静态检查，不冒称客体验收。
  使用方法与限制见e08.md；无TLS/动态插件，捆绑zlib静态链接。
- 显式离线 work_disk.py 可 mkdir/import/export，拒绝覆盖目标；运行时文件/装载
  都在客体，不由宿主代执行。

## 当前E08-2/3 最终证据

构建5276ff16bb6470b0；源码SHA256：
5276ff16bb6470b0b5dd25b3516e819929e617a8f74147e0205440ed4085a110。
xos.img SHA256 7f4e361efed1c8b40470b30bfdb859d7d95c7bea13cfbfa3504949f82b28513a。

- make smoke：79组通过，包含5组E08-2及旧74组；另7份许可材料检查通过。
- 显式binutils_smoke：7组通过，32次实际命令，包含两轮完整链路、索引前后检查、
  同文件保护、汇编/链接错误、插件拒绝、源码逐字节保留、每步资源复原和同步重启。
- E08-3压力测试（2026-10-24，5276ff16）：S0/S1/S3/S4通过；S2的34成员archive
  final `ld` 报成员unknown architecture（首次21.o，probe中0.o，首个失败成员不稳定）。
  不是对象生成错误；host对象/archive有效，guest `ar t`和`ld -r`可读。E08-3压力
  不算全绿，S2当时是E08-4 archive/GCC前的blocker；0017已定向修复，见上。报告：
  `e08.md`、`build/e08_3_stress_combined.json`。
  生成ELF及stripped ELF均输出seed chain并退出42，宿主readelf/nm仅静态核对。
- make build同源重建完整manifest相同，193个产物、260个源码哈希均核对通过。
- Seed构建指纹47ddd3071e2ad7f69b8b903c51b491aa59d81ed96e173fb0f506341248af0a9e，
  目录.cache/xos_seed/binutils/build/下，manifest SHA256
  1673edded076b3a8e001fc538ec52a452c38d4f2a7a115e7190fbdc2f69f3ef0。
  SDK快照765f556c…绑定实际CRT/库哈希，虽全局build_id早于最终测试文件，逐项与
  当前SDK链接输入一致并由测试核对。没有宣称GNU独立全清理重编的位一致性。
- 原始证据：build/manifest.json、各正式smoke_report.json、binutils_smoke_report.json、
  e08_rebuild_check.json、license_report.json、binutils_*静态检查与串口日志；关键哈希
  保存在0015。as_preflight_report.json保留早期TLS失败，不是最终gate结果。

不能将下列E08-1历史基线哈希当成本轮最终版本。

## E08-1 完整基线证据

构建 ID：f3c198eb5044cb15；源码 SHA-256：
f3c198eb5044cb15beb1883e6809cde4cc3db52294d0004335e75ec6616e9885。

- kernel.elf：5774a6414ff5ad9250f301223a0bbe7c54b736c4551caf7f849db0c03fbe4820。
- kernel.bin：274460 字节、537 扇区；972776c5c3735954ad2fe45894c0bdcf9997a9f91d6758ec18888061691e3026。
- xos.img：74b77c85018cc8a88f695836982299b5cf70de594f71e72f4e5f2acff77e1931。
- 磁盘专用 e08_probe ELF：277808 字节；fed961ca05f96725403f12823994304e2a15d046b2ae268ed501e8ab5b7887fa。
- make smoke：6+18+12+13+8+4+1+3+9 = **74 组通过**，另 7 份许可证材料检查通过。
- 新 gate：两种 FAT32 容量、大 ELF/BSS、子进程路径/目录/改名/空格名字、256 KiB
  流式保存/逐字节导出比较/双启动、非法 ELF 回滚、并发会话、保存冲突、取消清理、
  65536 页上限和全部页表回收。旧 FAT16、物理满盘、ELF ASan/UBSan 与通用代码
  AArch64 编译检查继续通过。
- 最终样本：512 MiB/2 GiB 盘原始 ATA 读 6.52/6.74 MiB/s，经文件服务读取
  3.96/4.14 MiB/s；65536 页压力含撤销约 0.396 秒。固定 TCG/缓存下单次样本，
  不是 GCC 性能/冷缓存/真机证明。支持继续保留预载方案，尚未测真实 Seed 峰值。
- 同源码重建完整 manifest 与全部产物哈希相同，所有源码绑定核对通过。
- 已查看 build/e08_2048_screen.png：重启后 verify 输出 BSS/path/stream/sync=ok、退出 0。

原始证据在 build/manifest.json、各 *_smoke_report.json、e08_storage_smoke_report.json、
e08_rebuild_check.json、license_report.json、e08_*_serial.log、截图。关键结论及哈希
亦保留在 0012，清理 build/ 不会丢失交接结论。工具版本仍为 GCC/G++ 16.2.0、
Binutils 2.47.20260726、NASM 3.02、QEMU 11.1.2。

## 许可证与未来图形方向

自研新代码 Apache-2.0；历史 MIT 基线/声明保留，第三方原条款保留。管理见
licensing.md、licenses/components.json、LICENSE/NOTICE；SDK 实际携带并记录哈希。
本次许可确认与材料检查记录见 work_log/0014_license_management.md。
newlib 为多来源条款，不能统一标为 LGPL。当前库逐成员许可证追溯尚未完成，
不因材料检查通过就声称法律/组件审计全部完成；未来 GNU Seed 分发另核实际条款。

用户于2026-10-24确认Qt为GUI主线、SDL为次选，取代此前SDL优先方向。
xos_plan.md v0.5已新增E13–E20与G01–G10：运行基底、显示/输入、QtCore、
QtGui/QPA、Widgets、无界面QML、软件Quick、集成/试用分别验收。
版本/feature/线程与资源预算按阶段冻结；Qt原生重建另验，不作为首窗前置。
窄OS服务与用户态Qt/SDL适配分开，不绑定固件/ISA；尚未引入Qt或开始GUI实现。
本组仅文档修改，责任已结束；交接见work_log/0016_qt_gui_plan.md。

## 下一步：dash C / xsh交互；E09试用反馈待补

先读e08.md、e08.md、e08.md。

1. E09发行交付已由0023完成，镜像/工作盘/SDK/源码/说明公开；朋友独立试用与
   备份恢复/升级的真实记录待补，O19/O20仍未验，不阻塞可选dash和xsh后续开发。
2. dash B0/B1已由0028通过，B2已由0042通过；下一批是C阶段管道、隔离执行和兼容收口。
   后续压力继续专人负责，使用0022正式派生G++/目标库及0020修复C/binutils；
   不复用含已暴露bug的原始工具。已有功能测试不无变化重复运行。
3. Qt主线/SDL次选仍按v0.5的独立阶段，当前未开工；系统重建和自举也另行验收。

当前已有受限GCC/G++及目标标准库基础设施；尚无完整POSIX/完整C++标准库、动态链接、UEFI、SMP、服务重启、sysroot 只读授权或任意掉电保证。
E08当前受限功能范围已完成，O11–O13按0022固定静态配置通过；其他O条目不自动改标。
