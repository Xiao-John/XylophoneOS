# CPython 移植计划：先把 Python 交到朋友手里

2026-10-25，0029。用户根据朋友投票将 CPython 列为优先应用移植目标；本轮只规划，
实施交给专门的用户态移植 agent。本文细化 E12 与 userland_port_catalog.md 的
PY0–PY4，不取消正在进行的 dash 工作，也不把 Python 变成 E09 的补验门槛。
选型和配置是待实际构建验证的建议；下列 gate 全部尚未运行。

0030更新：PY0a/PY0b 已通过（静态解释器、`-c`、脚本、Unicode、异常、GC、
同目录 import、重复启动）。fingerprint `ad85d8438b4101d66483`，证据
`build/cpython_py0b_report.json` 与 [工作记录](work_log/0030_cpython_py0.md)。
固定哈希种子、自旋 sleep、无墙钟/熵/线程等限制已记录，不因通过而改标为完整
POSIX 或完整标准库。下一批 PY1 脚本路径/argv/import 规则，再 PY2 REPL 与存档。

0031更新：用户确认[公共线程契约](threading_contract.md)，E13-T现在前移。PY0可以
保留单线程bootstrap；主端依次交T0/T1/T2，T2冻结后本移植立即接T3-PY真实pthread
后端，不再等PY3压缩/包/进程等其他生态功能。0030源码/探针按其回执独立推进。

0038更新：PY1已通过。由已接受的PY0 fingerprint生成560文件的确定性stage和逐文件
SHA256清单；客体验证argv/cwd/env、脚本目录优先导入、无宿主路径泄漏、二进制文件
原样读取，以及json/re/collections/itertools/functools/math的选定操作。缺模块、语法
错误和未捕获异常均退出1并回到Xsh。证据见`build/cpython_py1_report.json`与
[工作记录](work_log/0038_cpython_py1.md)。这不扩大到全标准库、REPL/input或存档；
下一批仍是PY2。

## 第一份可玩的交付

从 Xsh 输入 `python3` 进入传统 `>>>`，能算数、定义函数、处理字符串；能执行
`python3 hello.py`、导入同目录模块、读写工作盘文件。提供一个显式设定随机种子
的猜数字或文字冒险，以及 JSON 存档示例。Python 正常退出或失败后回到 Xsh。
保持 CPython 的语言语义，不另造 Python 方言；具体 OS 功能按支持矩阵报告。

第一条启动链是 **Xsh → 普通静态 ELF → CPython**。脚本由 `python3 file.py`
显式解释，不要求内核识别 `.py`、shebang 或 Python 对象，也不要求 dash 代启动。
纯解释器不因可能将来执行子进程而要求构造权。Python 本身不是安全沙箱。

## 版本与构建选择

- 推荐 CPython **3.14 系列的维护版本**。查询时官网列出 3.14.9；PY0 先取得其
  官方源码包、验证来源并冻结摘要。3.15 已发布，但第一次移植先减少新版本变量。
  不为逃避接口依赖退回已结束维护的 Python 2 或早期 Python 3。
- 本轮读到的内部实现为官方 **v3.14.0** 源码，属于架构勘查，不是 3.14.9 源码
  审计。实际版本的线程、锁、时间、初始化和构建选项必须重新核对；未冻结源码包。
- 宿主交叉构建，目标为 XOS 静态 ELF；先不开动态 libpython、JIT、free-threaded、
  PGO 或 LTO。GIL 保留，bootstrap仅一个真实用户线程；T2后接真实pthread，
  保留GIL多线程，不把free-threaded作为首版目标。
- 同一份固定源码构建匹配版本的宿主 build Python，供冻结模块和代码生成使用。
  宿主生成器运行与 XOS 解释器运行分别记录，不能用宿主 Python 代验收。
- 首先评估 `--without-mimalloc`，必要时也关闭 pymalloc，走已实现的 libc 分配。
  选项以固定版本 configure 为准。没有真实 mmap 就不定义 HAVE_MMAP；不能因为
  SDK 有声明或 ENOSYS 桩，就声称系统支持该能力。
- `Modules/Setup.local` 固定静态内建模块；逐个保存启用、禁用和失败原因。目标
  pyconfig、sysconfig、链接参数均来自 XOS SDK，不复制 macOS 的探测结果。
- `sys.platform` 应识别为 `xos`，不伪装 Linux；`os.name` 若采用 posix，须与
  实际 posix 模块和功能声明一致。第一批不承诺可作为通用 POSIX 平台。

## PY0 必须先回答的运行时问题

以下是源码和既有报告的观察，不是冻结SDK的能力承诺。0031核对时0028已交付；
先获取其最终SDK回执，再做最小目标探针。0030的旧快照探针保留原版本绑定，
E13-T新SDK另建profile，避免用旧配置覆盖新实现。

| 缺口/风险 | 首批处理与判据 | 所属层 |
|---|---|---|
| 原生线程缺失，CPython 内部仍使用锁/TSS | 临时bootstrap审计单线程路径；主端按E13-T交付T2后立即接T3-PY真实pthread | 主端公共机制/SDK；移植agent做CPython后端与gate |
| 单调时间与墙钟 | 先提供真实单调时钟来源及分辨率；墙钟不存在就明确不可用，不把 uptime 冒充 Unix 时间 | 公共窄时钟接口；PC RTC 放平台层 |
| 哈希种子/熵 | 开发启动可显式固定 hash_seed；安全随机接口不得伪造；一般分发前单列熵来源 gate | 初始化配置/后续熵服务 |
| 启动 import 与编码 | 固定 importlib、encodings/codecs 及其实际依赖闭包和路径；验证无宿主路径泄漏 | CPython 构建与安装布局 |
| stdin 的空闲、EOF、短读 | 核对冻结 SDK：原始 UART 无数据不能当 EOF；REPL/input() 要有真实等待和行编辑桥接 | 先 port-local 控制台适配 |
| newlib 格式化与宽字符/locale | 用目标探针验证 snprintf 的 %zu/%zd/%lld、va_list、浮点、必要转换函数；缺项追到真实库实现 | libc/配置，不用格式宏掩盖错误 |
| 小栈、堆与静态 TLS | 正确报告/限制 C 栈，测试递归拒绝、GC、内存失败和退出回收 | CPython 栈探测/现有 SDK |
| 文件与目录细节 | 探测短读写、seek、errno、目录遍历、stat、关闭与文件数上限；不假报权限/符号链接/时间戳 | 文件服务/libc |

### 单线程并不等于“删掉所有线程代码”

官方 v3.14.0 的 `Python/thread.c` 存在 HAVE_PTHREAD_STUBS 路径，其 TSS 有实际
状态，创建线程返回失败；但 mutex/condition 的部分函数是无操作。它为受限平台
提供线索，**不是 XOS 已有可靠 pthread 的证明**，也不是简单 configure 开关承诺。

实施者需检查固定版本的 PyMutex、parking lot、信号量、GIL、超时和最终化调用链：
仅在一个线程且不会依赖不存在的等待/唤醒语义时才采用此私有 profile。验证重复
初始化/退出、GC、锁获取/释放、非阻塞获取失败及有界超时；不允许忙循环永不返回。
`_thread` 等 bootstrap 必需模块不能按“可选”随意删除；线程创建要明确失败。
第一批不承诺多解释器并发或任意第三方 C 扩展。若该路径不可用，先交具体阻塞
调用栈与所需原语，由主端补真实机制；不向全 SDK 塞成功返回的 pthread 桩。

### 时间、随机数与控制台

当前 gettimeofday 返回 ENOSYS，未见可用 clock_gettime；已有 uptime ticks 可作为
单调时间候选，须核对频率、溢出与分辨率。v3.14.0 的普通非苹果 Unix 路径
`_PyTime_Init` 本身直接成功，因此不能断言“没墙钟一定无法初始化”；仍须检查
启动其他路径和 time 模块。time.time、sleep 等只在其真实语义通过后开放。
实现时钟应复用于 Qt 等后续消费者，解释器里不读取 CMOS 或绑定 x86 指令。

固定 hash_seed 只用于显式的 bootstrap/testing profile，不当作安全熵。该 profile
可先交朋友测试，但必须在能力清单标明；os.urandom/secrets 不提供假数据。
`random` 导入可能依赖时间和熵，不能只看到 pure Python 就判定可用；小游戏用
显式种子，并验证实际导入路径。安全随机和每次启动的哈希随机化另行验收。

传统 REPL 使用 PYTHON_BASIC_REPL 配置，先绕开新的 Python REPL/readline/termios
依赖。若启动配置禁用了环境变量，必须让选择真正生效，不能只在文档写 export。
`input()` 与 REPL 必须共用验证过的输入语义，不能只修最外层提示符。覆盖 CR/LF、
退格、空行、空闲等待和 Ctrl-D；超长行拒绝整行，不能执行截断前缀。Escape 保留
现有监督取消；Ctrl-C/KeyboardInterrupt 等待真正中断机制，不借信号空桩冒充。

既有 0025 记录了 %zu 探针在 strlen/0x9 故障，改用 %d 后通过；根因仍未确认。
这是新 libc 探针的输入线索，不是已经坐实的“所有 C99 printf 均不支持”。
当前调用栈 32 页（128 KiB）、总用户页上限 65536 页（256 MiB，包含其他映射）；
需处理 CPython 对 pthread 栈查询/默认栈大小的假设，不能只提高 recursionlimit。
简单工作负载先以 64 MiB 为观察目标，记录实测峰值再调整，不承诺已达到。

## 安装、模块与编码

建议布局为 `/usr/bin/python3`、`/usr/lib/python3.14/` 和独立示例目录；不覆盖
已有文件，不自动创建 `python` 别名。先保留未压缩的标准库目录；只有 zlib 已验收
后才采用需要 deflate 的 zip 包。启动模块也可冻结进 ELF，必须由同版本生成器
产生并记录清单。不能只打包解释器，等首次启动才发现 encodings 找不到。

使用 PyPreConfig/PyConfig 显式控制 UTF-8、模块搜索路径、site 导入和信号处理；
bootstrap 可关闭 site、字节码写入和环境自动探测。进入脚本阶段后保留脚本所在
目录的导入行为，明确 cwd/PYTHONPATH 规则，测试优先级；不能靠永远 isolated
模式而破坏最常见的 `import helper`。若提供 .pyc，须绑定相同版本 magic；文件
时间不可靠时先关闭自动缓存或使用真正支持的 hash-based 缓存。

UTF-8 文本、Unicode 对象与 Unicode 文件名是不同 gate。当前路径协议有限制，
ASCII 路径先行；UTF-8 内容可单独测试，不承诺终端能绘制所有字符。避免依赖
宿主 locale 数据。安装要检查文件容量、目录容量和模块导入深度下的 FD 高水位。

模块支持清单至少分四类：内建且已验、纯 Python 且已验、明确不构建、被真实
底座阻塞。导入成功不等于全部方法可用；os.supports_* 等能力集合必须真实。

- 首批语言：整数/浮点、容器、函数/类、异常、迭代器、生成器、GC、Unicode。
- 首批模块目标：sys、builtins、io、os 的文件子集，及 math、json、re、collections、
  itertools、functools。按实际依赖闭包逐个验收，不承诺列出即全部随 PY0 提供。
- 后续高收益：zlib、hashlib 的选定算法、sqlite3、pathlib、argparse、dataclasses；
  每项检查导入和调用闭包，不能凭“纯 Python”直接判定成功。
- threading的真实并发按E13-T/T3-PY前移；动态.so、ctypes/libffi、socket/ssl、
  multiprocessing、subprocess、完整signal/asyncio继续按各自底座推进。Qt 为 GUI 主线，Tkinter 不作为本移植前置。
- 离线纯 Python 包可早于 pip：用已审查包验证 import。之后才考虑 wheel 安装、
  venv 和 pip；manylinux 二进制 wheel 不因 ISA 相同就兼容 XOS。联网 pip 还依赖
  网络、TLS、真实时间及证书信任，不能用关闭证书验证抢跑。

## 批次与验收

各批只运行对应新增/受影响的目标测试。专人负责压力，移植者不重复旧全量压力；
资源回到基线的少量生命周期测试属于功能 gate，不替代压力结论。

| 批次 | 可独立交付的结果 | 必须保存的客体证据 |
|---|---|---|
| PY0a：依赖探针 | 源码/SDK 锁定、configure 能力表、上面各缺口的最小探针；尚无完整解释器也可交接 | 每项真实支持/失败/未运行，缺符号与行为错误分开；需要主端补的精确契约 |
| PY0b：核心 | 静态 ELF；`-c` 的算术、Unicode、异常、GC 和退出；解释器初始化可重复 | stdout/stderr/状态码，初始化失败诊断；少量重复启动回收；禁止宿主代执行 |
| PY1：脚本与 import | 工作盘 .py、argv/cwd/env、同目录模块、选定标准库闭包 | 缺模块/语法错误/未捕获异常非零退出；路径顺序；无宿主路径；脚本原文不变 |
| PY2：朋友可玩 | 基本 REPL/input、文件/目录、JSON 存档、选定 math/re；退出回 Xsh | 空闲不 EOF；Ctrl-D/取消；短读写与失败；sync 后重启再读存档；峰值及回收 |
| PY3：按需扩展 | 熵/压缩/数据库/离线包及后续子进程/动态扩展；公共单调时钟与线程按E13-T前移 | 每个能力独立gate；T3-PY单列，subprocess不因posix_spawn存在自动通过 |
| PY4：批次发行 | 对已通过的 PY0–PY2 与选定 PY3 做可分发收口；朋友独立试用 | 固定模块矩阵、清单/哈希/许可/安装回滚方法、独立试用记录 |

**第一里程碑是 PY0–PY2 后做一次 PY4，不等待 PY3 全部完成。** 上游 test 套件按
依赖选择，例如核心、Unicode、GC、json、re 的合适测试；每个 skip 说明原因。
不追求通过修改断言把整个 test_os/test_posix 涂绿，也不把崩溃后的重启当退出成功。
原生构建 CPython、自举或依赖它重建 XOS，属于后续 E10/E12 能力，不混入交叉移植。

## 文件结构、分工与交付

实施时按实际需要建立目录，本轮没有建立源码骨架：

```text
src/ports/cpython/
  source_lock.json        # 官方包/摘要与版本，不存凭据
  patches/                # 上游补丁，按职责拆分
  config/                 # XOS profile、模块清单、能力探测结果引用
  upstream/               # 原许可/声明及本地修改说明，依现有 ports 惯例
scripts/build_cpython.py
tests/cpython_smoke.py
tests/fixtures/cpython/
docs/reports/cpython_<batch>_handoff.md
```

构建 cache 使用 `.cache/xos_seed/cpython/<配置摘要>/`；宿主工具、目标对象分目录。
每份产物绑定源码、补丁、SDK、配置与模块清单摘要。客体 runner 使用专用盘与
独立系统/输出目录；共享 build 和系统重建仍由主端排他串行安排。

用户态移植 agent 负责以上 port、本地桥接、交叉构建、模块闭包和新增测试；
主端负责评估公共 ABI/libc/文件/时钟缺口。先交“调用方 + 所需语义 + 最小失败
探针 + 是否阻塞本批”，再确定公共实现，不能双方同时修改 libc 或内核。
等待真实底座时可继续做宿主生成器、模块整理和许可证，不用未实现接口假跑。
构建/安装/客体运行分别给回执；每批报告真实命令、版本、产物哈希、错误、未运行
项和下一步。实现开始前在 state.md 重新领取范围，0028 占用区不得直接开改。

移植者第一条任务：**先做 PY0a，再做 PY0b；拿到解释器 `-c` 回执后再扩模块。**
允许开发 hash_seed profile，必须显式标记；不得对外声称完整 Python/完整 POSIX。

## 许可证与资料

CPython 保留其 PSF 等原始授权及随附第三方许可；不能统一改成 XOS Apache-2.0。
按实际静态内建模块记录引入组件，例如启用 expat、mpdecimal、zlib、SQLite 时各自
审查。同步 licenses/components.json、原始 LICENSE/声明、来源/摘要、本地修改
说明与发行材料；新自研桥接按 Apache-2.0。未引入源码时不虚构已完成组件审计。

本轮依据（官方文档与源码；查阅日期 2026-10-25）：

- [版本与维护状态](https://www.python.org/downloads/)
- [交叉构建、模块和分配器选项](https://docs.python.org/3.14/using/configure.html)
- [传统 REPL 选择](https://docs.python.org/3.14/using/cmdline.html#envvar-PYTHON_BASIC_REPL)
- [v3.14.0 线程后端选择](https://github.com/python/cpython/blob/v3.14.0/Python/thread.c)、
  [单线程后端](https://github.com/python/cpython/blob/v3.14.0/Python/thread_pthread_stubs.h)、
  [后端类型和限制](https://github.com/python/cpython/blob/v3.14.0/Include/cpython/pthread_stubs.h)
- [内部锁](https://github.com/python/cpython/blob/v3.14.0/Python/lock.c)、
  [parking lot](https://github.com/python/cpython/blob/v3.14.0/Python/parking_lot.c)、
  [bootstrap 模块](https://github.com/python/cpython/blob/v3.14.0/Modules/Setup.bootstrap.in)
- [时间](https://github.com/python/cpython/blob/v3.14.0/Python/pytime.c)、
  [启动哈希](https://github.com/python/cpython/blob/v3.14.0/Python/bootstrap_hash.c)
- [CPython 许可证与第三方条款](https://docs.python.org/3.14/license.html)

本轮只完成勘查和设计：少量官方源码下载到独立规划 cache；未构建 CPython、
未运行 XOS 客体测试、未修改 SDK/内核/loader、未发布新产物。
