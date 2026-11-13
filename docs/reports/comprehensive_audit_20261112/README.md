# XOS 全仓审计与修复说明（2026-11-12）

## 结论和边界

本轮从上游 `Xiao-John/XylophoneOS` 最新 main 开始，先同步了 UTF-8 M2 边界探针，
收尾又纳入刚合并的 IPC IP5。最终审计基线为
`4c9b6f8feb0667d7169167e406da662be789876c`（#114）；相对前一基线
`e6246faf8eefac305a99528f727b1592ee93a5b2` 的 15 个增量文件已另行复核。修复在独立
`codex/comprehensive-audit-20261112` 分支交付；未合并、未发布新发行版、未改写历史验收。

已经逐文件审阅当前可见的自研内核、启动、共享 ABI、用户运行时、服务、程序、
GUI/SSG、端口适配、构建脚本和测试；也补读了全部可见第三方文本代码及冻结报告中
保留的代码快照。全仓文件盘点与逐文件阅读是两种不同证据：完整路径清单见
`repository_inventory.csv`，每项标明实际阅读方式。相同历史副本通过逐字节比较，
不同副本通过完整差异与已读源码对照复核，未冒记为重新通读。
第三方源码归档内部、预编译库内部、美术资产和非代码数据不在源码全读声明内。
本报告不证明“项目所有 bug 已清零”；也没有反汇编审计全部二进制。

基线共 **5,250 个跟踪文件**，其中 **1,174 个可见代码、补丁和构建输入文件**全部有
逐文件审阅记录；本轮新增的 **18 个实现/回归文件**也已复核。这里不把二进制归档、
压缩包内部源码、游戏 YAML 数据或全部历史报告文字算作已逐行代码审计。

下表共 **57 项修复或待办处理**：24 项运行代码问题、29 项构建/测试/证据工具问题、
3 项交付材料与文档待办、1 项参考模型问题。这是按问题类别去重后的条目数，
不是“57 个客体 bug 已验收”。完整逐条说明与未验收边界同时交付。

本机可用 GCC/G++、ar、nm 和 Python；缺少仓库固定的 x86_64-elf GCC/G++ 16.2.0、
Binutils 2.47.20260726、NASM 3.02、QEMU 11.1.2。实际运行系统构建在 NASM 检查处失败。
宿主编译和测试能验证下述具体实现，但没有验证 BIOS 启动、真实调度、TLB、硬件中断、
DMA、Qt 客体界面或完整发行流程。未用其他编译器冒充固定工具链，也没有把参考模型
或历史 PASS 当成本修订的客体 PASS。

### 实际验证摘要

| 验证 | 本轮结果 | 能证明的范围 |
|---|---|---|
| unittest：24 个模块 | 256 项：253 通过、0 failure、2 error、1 skip | 两个 error 是缺少旧 SDK；一个 skip 是缺少 idna XPK，未隐藏或降级 |
| 真实 files/FatFs 回归 | 文件语义 25/25；故障恢复 21/21 | 内存盘和实际磁盘写错误注入，不是实际设备断电验收 |
| 真实 libc/loader/file_client 链路 | 启动描述符 15/15；execvp 边界 6/6 | 宿主替代 syscall/IPC 边界，未执行目标内核 |
| IPC 新旧 SDK 查询兼容 | 9/9 | 真实历史/当前头与当前内核查询分支，syscall/页合法性/计数设置为宿主边界 |
| Interactium 与 transport | ASan/UBSan 两套通过 | 实际服务实现；容器中关闭 leak detection，不宣称完成泄漏检查 |
| SQLite、dash、Adventure、ABI、归档等 | 对应真实实现或真实 CLI 定向回归通过 | 详细命令和边界在附件；与 unittest 有重叠，不累计成虚假的独立总数 |
| Python/shell 语法 | 430 个 Python 中 429 可解析，1 个是有意 syntax_error 负例；27 个 shell 语法通过 | 语法检查不是完整执行 |
| 内核对象编译 | 初审默认 22 个、VM1/COW1 另 3 个；最新 tasks.cpp 三配置重跑通过 | 宿主 g++ 和生成头声明替身，未链接/启动系统；没有把初审批次改称全部在新基线上重跑 |
| `make build` | **BLOCKED，退出 2：NASM 不存在** | 固定工具链、QEMU、Qt、SDK 和完整发行验收未完成 |

两项缺 SDK 的 unittest 为 `package_p0_cases` 的独立 C/C++ 工程与 SDK binding/init
拒绝测试，要求 `build/releases/0.0.1-1024`。锁定 newlib 表的宽度对照与 FB12 实际
符号绑定测试也缺少对应源归档/客体证据；原始前置条件失败在汇总中保留。

## 已修复问题

下表的“宿主”是本轮执行结果；“客体待验”表示代码已经修复，但新系统镜像尚未构建运行。
命令、实际返回值和限制另见 `validation_results.json`、`validation_commands.txt` 与各专项说明。

| 编号 | 触发与影响 | 修复及验证 |
|---|---|---|
| K01 | 父进程线程 A 等待子进程；完成后 A 已唤醒但尚未取结果，线程 B 抢先 wait，消耗完成记录，A 得到假成功且遗留 VM pin。 | 把既有重复等待检查前移到 ready 分支之前；真实 tasks.cpp 片段回归覆盖阻塞/轮询竞争、跨页 copyout 与 pin 释放。旧实现稳定失败，修后通过。 |
| K02 | monitor 连续 `alloc; alloc; free` 覆盖唯一记录的页地址，第一张页无法释放。 | 已持有页时返回 busy；真实 console/memory 宿主回归恢复页数基线，kernel smoke 增加相同客体用例。 |
| K03 | 最新 IP5 在原 72 字节 ABI 的旧零保留字中默认返回直切计数；计数非零后，真实旧 SDK 的 feature query 稳定返回 -112 并清空输出。 | 通过既有 arg3 的 query 专用 0x1 位显式选择计数，默认保持零；SDK 默认兼容、IP5 两处主动取数。旧/新 SDK、0/1 累计、未知 flag 和非 query flag 共 9 场景通过；未修 IP5 的相同回归失败。 |
| F01 | seek 到 EOF 之后写入失败，逻辑偏移被回滚为 EOF，后续重试写错位置。 | 仅将 FatFs 游标钳到合法位置，保留原逻辑偏移；真实文件服务回归通过。 |
| F02 | 活动原子保存尚未完成时，另一个无关文件的 rename-replace 清理了其 staging 临时文件，导致全局 recovery gate。 | rename 只清理自身 journal/backup，保留活动 staging；真实文件服务回归通过。 |
| F03 | replace_chunk 部分写入后返回错误，却未累计已写入长度；重试可能重复数据。 | 无论最终错误与否都记录真实进度并回传；真实短写/错误回归通过。 |
| F04 | replace_abort 清理失败仍报告成功。 | recovery_failed 时返回 I/O 错误；故障注入回归通过。 |
| F05 | O_TRUNC 的同步与随后关闭都遇到真实磁盘写错误，错误分支仍丢弃持有 FatFs 共享锁的 FIL；磁盘恢复后文件依然 busy。 | 成功打开后立即登记对象，失败时进入现有零引用清理重试；真实 files.cpp + FatFs + disk_write 故障回归旧版失败，修后文件语义 25/25。 |
| L01 | startup open_paths 重定向时，open 直接复用了 fd 0/1/2，初始化逻辑又把它自己关闭。 | opened 等于目标 fd 时保留新描述符；真实 libc + file_client 的 15 组标准流组合通过。 |
| L02 | execvp 为末尾已有 `/` 的 PATH 分量重复添加分隔符，合法的 255 字节目标被误报 ENAMETOOLONG，或错误跳过首个候选。 | 仅在需要时加分隔符；真实 execvp、execve、loader、file_client 调用链的 6 个边界场景通过，旧版其中 2 项失败。 |
| S01 | audio 服务启动返回正 PID，调用者却只把 0 当成功。 | 内部确保服务接口统一返回成功 0；启动、复用、失败、重试等宿主用例通过。 |
| S02 | `type display-start` / `type interactium-start` 把内建命令误判为外部程序。 | 补齐 builtin 名单；同一 supervisor 宿主回归通过。 |
| S03 | 裸 `diag` 落入外部程序查找并提示 not found。 | 显示正确用法；已补 SL3 客体断言，客体待验。对应 BT-02。 |
| P01 | xypm help 允许 `ensure --sha256`，实际参数分发直接拒绝。 | ensure 与 install/upgrade 使用同一五参数分发；真实 CLI 已验证进入维护租约检查，而非 usage 拒绝。未把边界回归冒充一次成功安装。 |
| I01 | 长按按键、切换焦点后的重复 press 覆盖原 release 所有者，原窗口可能一直保持按下。 | 重复 press 保留原 owner；真实 Interactium 服务回归先失败后通过，ASan/UBSan 通过。 |
| I02 | PS/2 输入重同步只发给当前焦点，其他窗口遗留 held key。 | 重同步发给相关持有者并清空状态；真实服务回归与 transport 检查通过。 |
| I03 | Notes 打开 A 后编辑，将路径框改为 B，再点 Open / Save and continue，会把 A 的编辑内容覆盖到 B。 | 保存当前 loadedPath 后再打开 B；普通显式 Save 保留路径框目标语义。未命名缓冲区要求先保存；源码路径复核完成，Qt/客体待验。 |
| I04 | 浏览器先把被拒绝 href 解析为空，再把空字符串解释为当前页，错误重载并追加历史。 | 将原始 href 送到最终导航入口，保留拒绝语义；Qt/客体待验。 |
| I05 | interactium_demo 在显示服务永久错误时无限循环，重绘失败还以成功退出。 | 区分 again、等待失败和永久错误，错误时非零退出；4 条真实程序边界回归通过。 |
| I06 | 终端服务死亡后，命令行编辑器不断 yield，无法回到 supervisor 的恢复逻辑。 | 调用已有 terminal recovery；恢复后只丢当前未完成输入行，保留编辑文档和 dirty 状态；3 条真实 file_ui 回归通过。 |
| A01 | Adventure 的 readline 将管道 EOF 当作暂时无数据，程序永不结束。 | EOF 返回已读的最后一行或空指针；真实 host pipe 的空输入、部分行和完整行回归通过。 |
| Q01 | SQLite xFullPathname 原样返回相对路径，切换 cwd 后 journal 可能落错目录。 | 构造词法绝对路径；真实锁定版本 SQLite 3.54.1 + XOS VFS 测试通过。 |
| Q02 | SQLite VFS 以路径字符串识别同一文件，不同名字/大小写别名不能共享锁身份。 | xOpen 一次 fstat，使用 device/inode 比较锁；真实 SQLite/宿主同 inode 别名回归通过。当前 XOS writer-busy 还会拦截一部分并发场景，未宣称已在客体重现数据损坏。 |
| D01 | dash 的初始 stdout 已关闭时，pipe 可占用 fd 1，后续 dup2 把读端覆盖。 | 安装标准流路由前将低号管道端点移到 fd >= 3；真实 pipe/fcntl/dup2 的四种 stdin/stdout 状态通过。 |
| B01 | ISO 目录记录缺少偶数长度文件名的零填充，长度边界也随之错误。 | 补齐记录填充，最大根名称由 220 调为 219 字符；直接检查生成 ISO 的记录、边界和文件内容。 |
| B02 | ISO 只生成 Type L 路径表，Type M 位置为 0。 | 补齐大端路径表并调整文件 extent；同一真实 ISO 输出测试通过。格式依据 ECMA-119 §6.9.2–3、§9.1.12。 |
| B03 | newlib/GCC/Qt 三套 archive 读取器接受截断内容/残尾，或静默合并同名成员，统计可失真。 | 共用严格 GNU ar 读取器；同名歧义明确拒绝。另实现归档哈希、成员集合、源哈希、build id 的清单校验，14 项真实 ar/文件回归通过。D12 仅部分偿还。 |
| B04 | Qt 来源脚本未比较归档 payload 与保留对象字节，就标为 object_record。 | 不一致时标明 object_record_byte_mismatch，不冒充一手来源；旧实现失败、修后通过。 |
| B05 | xypm host cache 的 SHA stamp 含非法 UTF-8 时崩溃，无法自愈。 | 解码错误按无效缓存处理，重新构建真实 helper；旧实现异常、修后通过。 |
| B06 | libc_audit 把 nm 的 archive 标题计为符号，并持续输出 E06 的过期 ENOSYS/64 KiB/TLS 结论。 | 从实际库符号与 SDK manifest 统计，明确只是链接符号清单；真实编译器/ar/nm 回归通过，完整 SDK audit 待构建。 |
| B07 | SSG P1 构建失败仍记录 BUILDING，缺编译器还把空路径当作目录执行。 | 明确 missing tool，并写 FAILED；真实失败入口前后验证通过。 |
| B08 | Qt portable receipt 完成脱敏后又追加绝对输入路径。 | 所有输入先加入，再统一 portable；真实脚本语句定向检查通过，未运行 Qt 全构建。 |
| B09 | Qt widgets 的 Windows Ninja workaround 在 POSIX 主机同样删除头文件依赖。 | 仅 Windows 应用原 workaround；POSIX 保留增量依赖，定向检查通过。 |
| B10 | P4A 验证函数 `scenarios = list(scenarios)` 遮蔽模块变量，必然 UnboundLocalError。 | 删除无用局部赋值；字节码/语法确认恢复模块读取。其历史镜像前置条件仍待单独处理。 |
| B11 | modern_apps_sources 无条件覆盖固定的历史 source_lock，丢掉后续追加的来源绑定。 | 已有冻结锁时在网络和写入前拒绝；实际仓库拒绝路径验证锁未改变。 |
| B12 | UTF8 SDK candidate 能借仓库头编译，却漏导出 sys/mman.h，独立消费者无法包含它。 | 沿用其他 SDK 的 sys 目录复制步骤；语法和源流程检查完成，完整 SDK 待构建。 |
| B13 | threading SDK 声称支持多层 logs-dir，父目录不存在时直接失败。 | mkdir 创建父目录；局部行为检查通过。 |
| B14 | release_smoke 使用 macOS 专有 `cp -c`，Linux 必然失败。 | 使用项目已有的 shutil.copyfile；旧命令在 Linux 的失败已复现，完整 release smoke 仍待固定依赖。 |
| B15 | newlib 下载/解压失败留下 SRC 空目录，重试跳过获取并永远找不到 configure。 | 完整解压后才发布缓存，旧空缓存可修复；真实 shell 配合下载/构建边界夹具的 3 项失败重试测试通过。 |
| B16 | C++ ABI probe 拒绝把输出放入 SDK/runtime 后，构建脚本的异常处理与外层 smoke 驱动仍往被保护输入写报告。 | 两入口共用既有输出范围检查，在任何报告写入之前拒绝；真实 build/smoke CLI 对四种非法输出位置均保持输入不变。 |
| B17 | ABI smoke 只在 builder 退出 0 时检查报告新鲜度；本次参数被拒绝后仍会读取旧 partial_not_ready 报告，甚至尝试旧客体用例。 | 新鲜度检查覆盖所有已有报告；实际 CLI 的未知 feature + 旧报告场景先失败后通过，不启动客体。 |
| B18 | SL3 Make 测试启动客体后，仍由宿主工具修改同一已挂载工作盘。 | 将已有脚本导入移到 Guest 构造之前；源码顺序与语法检查通过，未宣称复现客体磁盘损坏。 |
| B19 | binutils stress 的预期失败用例使用 code=None，实际完全跳过退出码检查，错误的成功退出也能通过。 | None 按仓库既有语义要求非零；执行真实 run 函数的 3 项宿主判定器回归通过，旧版 1 项失败。 |
| B20 | VirtIO GPU 可选隔离探针未提供时，报告仍把 MMIO/PCI I/O 隔离列为通过。 | 只在实际执行对应流程后加入成功检查；未提供参数明确写入 not_run。源码和语法检查完成，客体隔离未运行。 |
| B21 | 四个 Qt runner 将输入 ISO 复制为 boot.img，随后自动介质选择错误地使用 floppy。 | 保留原文件后缀；实际路径语句、Guest 介质分支和 QEMU 命令生成的 16 组宿主检查通过，没有启动 QEMU。 |
| B22 | dash/UTF-8/ISO 六个 runner 的七个 echo 标记会匹配终端输入回显，程序未输出结果也可能通过。 | 匹配独立结果行；与 B27 合计 10 个真实 Guest.expect 判定器场景：旧假输出均被接受，新版均拒绝，并接受真实结果串。未运行客体。 |
| B23 | 两个 bundle 负例没有测到声称的对象：non-ELF 用例没破坏 ELF，反斜杠用例改坏了偏移字段。 | 分别修改真实工具 payload 魔数与真实名称区，并要求对应错误；bundle 套件 26 通过、1 个缺包跳过。未声称修了新的解析器缺陷。 |
| B24 | 五个派生 SSG runner 只记录 pages probe 的源哈希，遗漏实际执行脚本的身份。 | 改为记录自身文件名；执行真实来源记录循环，五个当前脚本的路径与 SHA-256 均正确。旧冻结报告不变。 |
| B25 | pipe atomic fixture 仍把第三参数当旧保留位，期待 -2；当前 ABI 是绝对截止时间，已经可写应立即返回 0。 | 修正一处旧断言，与现有 ready 优先语义和其他探针一致；C 语法检查通过，客体待验。 |
| B26 | device ABI runner 在成功和异常路径都没有关闭 Guest，留下 QEMU 进程与磁盘。 | 在既有 finally 中调用 close；控制流和语法核对完成，未构造客体运行结果。 |
| B27 | 两个 ISO 烟测查询不存在的 hello 而非 hello.elf，并把输入回显当文件服务成功；bundle 安装的 stat 检查也只匹配输入里的名称。 | 查询实际文件名，并分别匹配解析结果与 size 输出；三个判定器与 B22 一并验证。客体待验。 |
| B28 | e08 压力测试接受 0 或负数 cycles，R1 可以一轮也不执行却标为 passed。 | 在参数入口拒绝 cycles < 1；实际参数解析语句核验，未改压力执行逻辑。 |
| B29 | e08 R3 实际生成约 0.4 MiB C 源文件，成功记录却固定称 1 MiB。 | 记录实际源文件字节数，保留原有压力规模；真实生成语句字节核验，未把报告修正冒充压力验收。 |
| T01 | 发行镜像缺少 PATH 中的 /bin，也默认没有 xos-diag。 | freeze/package/smoke 和文档已同步加入，按 system manifest 绑定诊断 ELF；新发行验收待运行，旧下载资产未变。对应 BT-03/05。 |
| T02 | Qt 修改通知只有最初 10 个补丁，漏登记后来加入的 qmalloc 包含修复。 | 补充第 11 个补丁及实际引入提交；不改历史统计、不冒充旧发行新增了该补丁。 |
| T03 | CPython 已知 exec_prefix 提示缺少面向用户的说明。 | Python 用法说明静态模块与标准库布局、检查实际输出的方法和真实导入错误的区别；按 BT-04 的文档退出条件处理，未声称警告已消失。 |
| M01 | IPC v1 参考模型的 caller-first 排队路径使用接收方 badge，丢失调用方 badge。 | 在 call_record 保留调用方 badge，新增 caller-first 用例；旧版 0 与 0xabc 不符，修后模型 19/19。仅为模型修复，未修改内核 IPC 或支持声明。 |

ISO 格式核对来源：[ECMA-119 第四版](https://www.ecma-international.org/wp-content/uploads/ECMA-119_4th_edition_june_2019.pdf)。
本轮新增缺陷回归测试实际实现或原样抽取的实现；涉及宿主边界替身的范围详见专项说明。
既有 IPC、COW、SSG 等参考模型另列验证范围，模型通过不能替代内核或客体验收。

## 尚未完成的事项：原因、影响与退出条件

### 1. 当前修订的真实系统和 GUI 验收

缺失固定工具链阻止 `make build`，因此也阻止 `make smoke`、VM/COW/IPC、音频、
Qt、SL3/SL4 和发行 smoke。宿主初审编译了 22 个 kernel/shared C++ 单元，另外
编译了开启 VM1/COW1 的 3 个对象；#114 合并及 K03 修复后又单独编译最新 tasks.cpp
的默认、VM1、VM1+COW1 三个配置。生成镜像头仅使用声明替身，没有链接启动镜像。
ASan/UBSan 测试保留；容器的 ptrace 环境不能跑 LeakSanitizer，相关测试关闭的是
leak detection，不能据此声称无泄漏。

退出条件：恢复 `config/toolchain.json` 对应工具和受信 SDK/seed，串行构建同一
commit，运行完整烟测及修改相关客体探针，绑定 system manifest/SDK/镜像，再运行
release smoke。不要把下载的旧镜像、宿主对象或旧回执作为本修订的验收替代。

### 2. VM3 / COW 仍属阶段性实现

普通 fork 仍使用 eager copy；隔离 COW1 不能直接解除开关限制。COW2 的跨页 copyout
需要先准备所有待写页，在 OOM/只读拒绝时保持约定的原子性，还要区分允许短进度的
I/O 输出。父进程退出当前会递归终止子进程，“父先退出、子继续存活”的 COW 验收需要
先完成生命周期设计。仅改一个 feature flag 会掩盖这些缺口。

退出条件：按 [COW 计划](../../plans/virtual_memory_cow.md) 和
[COW 契约](../../contracts/cow0.md) 完成生命周期、copyout、失败回滚与真实客体故障注入；
VM3 的 reserve/commit/decommit/protect/query、线程等待 pin 和进程退出必须联合验收。

### 3. IPC 最新状态与设备授权欠账

最新 #114 依据上游 #111 记录的三轮客体验收，已经将 endpoint_call、deadline、
notification、wait_set 四个位同时在 runtime 与双 SDK 开放为 `0x0f`；不能再把当前
主线写成全部 unsupported。IP5 短消息直接切换、handle 索引和批量复制也已合入，
其新客体探针与性能结果尚待运行。`bulk_grant_v1` 的 `0x10` 仍关闭。
本轮没有重跑上游的历史客体验收，也没有把它改绑为本轮组合结果。
`sys_device` 的请求校验后端仍返回 unknown，grant/map/DMA/IRQ/revoke 尚未完整落地。

退出条件：在本轮同一构建复验 [IPC 契约](../../contracts/ipc_v1.md) 的慢路径与生命周期
矩阵，并运行 IP5 的兼容性、回退、计数、资源和延迟分布探针；bulk 仍按 IP4 单独资格化。
设备授权按 [A2 契约](../../contracts/device_authorization_v1.md)
落地对象、回收和用户态驱动迁移，再接网络。硬件路径的延迟不能靠猜测调整。

### 4. 文件服务仍不是完整 POSIX

FS-01/02/04/08 仍在：同一文件多个独立写打开受 FatFs 锁限制；目录替换不完整；
打开实例不能 unlink/rename；cwd 仍绑定文本路径而非目录身份。它们影响编辑器、构建
工具和数据库，不能通过关掉 FF_FS_LOCK 或简单字符串规约解决。FS-03 的真正近满
FAT 介质客体测试仍未完成；现有故障注入只证明相应错误分支，不证明完整满盘设备路径。

退出条件：设计并落地服务端文件/目录 identity 和引用计数，补并发打开、延迟删除、
rename 后 cwd、短名别名、近满盘及崩溃恢复矩阵。保留现有失败 recovery gate。
见 [POSIX 子集](../../contracts/posix_subset.md) 和 [技术债总账](../../tech_debt.md)。

### 5. Python 线程、计时和音频

既有 Pillow 线程分配路径 `_malloc_r` page fault 尚无本轮可执行现场，不能靠猜测改
分配器或关闭线程。`clock()` 当前是单调墙钟近似，缺少每进程 user/system CPU accounting；
旧 CPython 独立时间适配仍有自旋睡眠。AU1/AU2 已实现，实际声波输出、服务死亡强制
静音与恢复还需 QEMU 音频证据。

退出条件：重建原始出错配置，保留 fault bundle、寄存器、栈和分配输入；定位线程
重入/TLS/堆边界后补实际回归。CPU 计时需调度器记账。音频按
[AU 计划](../../plans/audio_output.md) 验证，不用命令返回成功替代输出验证。

### 6. SSG / GUI 的历史竞态与尚未实测的修复

D13 的 Studio 首次运行超时、D14 的 consumer-exit/Notes shutdown 竞态仍未定位。
本轮输入路由修复没有证明这些超时已解决。Notes 保存路径和 Browser 拒绝导航已按
确定源码路径修复，但缺 Qt 构建环境，必须增加真实界面验证。QPA reply 目标容量不足
仅记录为未验证的异常回复风险；没有找到当前合法服务端触发路径，未为它加入推测性复杂度。

退出条件：同一构建保留服务退出、pipe close、watch ACK、窗口关闭的时间序列，能稳定
重现后修根因，再跑完整 stress。输入测试增加按键保持时换焦点、重同步和服务重启。
文本 M2 的新边界客体探针也尚待运行；码点处理不等于完整字素簇、locale 或输入法。

另有 **31 个旧图形 runner** 只启动 Display，当前 QPA 则需要 Interactium；部分还
期待第二窗口被拒绝，或匹配已退役的 Display 错误文本。精确文件清单见 `ui_review.md`。
它们需要按当前协议重建 fixture、定义多窗口和服务死亡预期，再做客体验收。本轮修正
明确的介质选择/判定/来源记录错误，没有直接放宽这些旧断言来制造通过。

### 7. 构建证据与交付债

D12 的统一读取器和内容校验器已经落地，但 newlib/GCC/Qt 的同次构建清单生成与正式
验收接入仍未完成。内容哈希一致不能证明捕获时点或声明分类正确，derived 结果仍须
保持 derived 身份。历史 P4A exporter/validator 有依赖 xos.iso/xos.img 的旧路径条件；
不能为了让新镜像跑旧报告而重新绑定冻结证据。

SL3 Make 的真实 C 项目以及 SL4 权限/env/cwd/fd 矩阵受缺失 seed/SDK 阻塞。
BT-07/08 的已发布 SDK/编译器仍是旧二进制；本次源码修复不会自动更新它们。
退出条件：生成新的受绑定 SDK/seed、清单和报告目录，运行独立消费者构建、make/嵌套 shell
与新发行 smoke。发布属于后续单独操作，本轮未发布。

### 8. newlib 依赖头的两项兼容缺陷

直接选择仓库可见 newlib 头时，宿主 GCC 14.2.0 已复现两项问题：`stdatomic.h`
在使用原生 `_Atomic` 标量的分支仍通过 `.__val` 初始化，合法 C11 程序无法编译；
`tgmath.h` 的当前分支不能保留 float/long double 的返回类型，后者还可能选到 float 函数。
探针、完整诊断和头哈希见 `newlib_header_results.json` 与 `kernel_review.md`。

影响取决于头搜索顺序：C-only seed 的 `-isystem` 可优先选到该头，C++ bundle 与
当前 xos_app 的 `-idirafter` 可先选 GCC 自带版本。没有证据表明全部交付应用都受影响。
退出条件是用固定 GCC 16.2.0 和实际 seed 分 profile 编译/链接复现，随后通过 newlib
源头补丁或明确的头优先级修正重建 SDK、来源清单与验收；本轮没有手改生成头或替换锁。

### 9. 原始 bug-hunting 题集与未覆盖范围

原题报告在被忽略的 `CONTEST/` 和桌面归档中。当前可达 main 历史、工作树及文件检索
没有找到这些原文件；仓库保留了修复日志和实际回归代码。详见
[bug_hunt_questions.md](bug_hunt_questions.md)。该文件是有来源的测试题目录，不能冒充
原始题集逐字文本。若需要原文，需提供 `CONTEST/` 或 `归档_副本.zip`。

预编译 newlib 内部和上游源码压缩包内部没有完成独立全量审计。
已执行输入/哈希/边界和相应真实实现回归，不把这等同于所有上游内部实现都被证明正确。

31 份现有计划及技术债的处置表见 `todo_disposition.md`。其中系统自举、SMP、完整网络、
xypm P3、Qt Quick/QML、完整多语言和故障包后续阶段属于尚未完成的开发工作；没有把
大项改成“已完成”，也没有重复实施已经被新主线替代的旧待办。

## 未来十项规划

| 顺序 | 工作 | 可判断完成的验收条件 |
|---|---|---|
| 1 | 固定并恢复可复现构建环境 | 在干净 Linux 环境安装锁定工具链，单命令串行构建同一源码；kernel/SDK/镜像来源可追溯，失败不沿用旧产物。 |
| 2 | 完成本轮修复的客体验收，再做补丁发行 | smoke、所有变更相关 guest、Qt 保存/输入、资源基线与 release smoke 全通过；新发行明确旧 SDK 兼容边界。 |
| 3 | 用文件/目录 identity 收口 POSIX 文件语义 | 多打开、延迟删除、目录替换、cwd 跟随 rename、真实满盘和崩溃恢复都有可重复测试。 |
| 4 | 完成 VM3 与 COW2/COW3 | copyout 准备/提交、pin、OOM 回滚、父子生命周期和资源回收联合通过；之后才评估默认 COW。 |
| 5 | 收口 IPC 新组合、快路径与 bulk 资格 | 在已开放的 IP2/IP3 上复验本轮组合，验证 IP5 的旧 SDK 兼容、回退、资源与延迟分布；IP4 bulk 独立验收后才开放。 |
| 6 | 落地设备授权并迁移驱动 | grant/map/IRQ/revoke 可用，驱动死亡能清理资源；随后推进用户态网络和真实音频输出。 |
| 7 | 修清运行库、依赖头与 Python 扩展的确定故障 | 按真实 seed profile 验证并修复 newlib 头兼容问题；重现并解决 Pillow 分配 fault；完成 TLS/分配/等待/退出组合测试和真正 CPU 时间记账。 |
| 8 | 收口桌面输入、编辑保存和 SSG 生命周期 | 覆盖换焦点长按、服务重启、A 保存后打开 B、consumer 退出；D13/D14 有根因和稳定回归；M2 边界有客体结果。 |
| 9 | 完成原生开发工作流 SL3/SL4 | 从独立 SDK 到 guest GCC/G++、Make、嵌套 dash 均可重建；权限、env、cwd、fd 继承矩阵通过，诊断工具默认可用。 |
| 10 | 把依赖来源记录移到构建时完成 | 每个新验收静态归档有同次生成 member_manifest；校验接入发布门；新报告与旧冻结报告严格区分。 |

顺序依据是减少后续验收的阻塞和数据丢失风险，不是按代码量排序。
第一、二项应先完成；复杂的文件身份、COW、驱动与网络应分开 PR 验收。

## 附件和复核

- `repository_inventory.csv`：基线全仓文件、类型及实际阅读覆盖。
- `validation_results.json`：实际运行结果、错误/跳过与验证范围。
- `validation_commands.txt`：执行命令与工具版本记录。
- `validation_log.txt`：关键结果与失败的规范化日志；`validation_reproductions.md` 给出一次性宿主检查的完整重放代码。
- `kernel_review.md`、`userland_review.md`、`ui_review.md`：分工审阅的具体证据和局限。
- `root_review.md`：ISO、构建、证据工具、发行流程与最终交叉复核说明。
- `latest_upstream_review.md`、`latest_upstream_results.json`：#114 增量复核、IPC 支持状态更正、兼容性修复及实际验证证据。
- `todo_disposition.md`：31 份计划及仍开放技术债的逐项处置和依赖。
- `bug_hunt_questions.md`：原题集线索、仓库保留测试和本轮新增测试题。
- `fatfs_truncate_results.json`、`newlib_header_results.json`、`ui_host_results.json`：失败/成功对照及明确的验证范围。
- `manifest.json`：本目录平铺文件清单，可由 `python3 tests/report_manifest_check.py` 校验。

对应工作记录：[b8f02808](../../work_log/b8f02808_comprehensive_audit.md)。
