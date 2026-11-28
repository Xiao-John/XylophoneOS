# 显式批准的在线 GNU 库 profile v1

本契约扩展 [公共 GNU 启动闭包](public_dynamic_runtime_v1.md)，允许一个独立
构建和标识的 profile 在启动后使用 `dlopen`、`dlmopen`、`dlclose`。
默认 fixed-startup profile 保持显式拒绝；新增路径没有新的 syscall，也不
赋予调用者从文件系统任意加载代码的权限。格式在
[ABI registry](abi_registry.md) 的 P1-K3 分配中先行登记。

## 批准对象、编码和映射

generation v2 保持 128-byte header 和 512-byte object。header offset 28
的 `online_mask` 只能选择 index >= 3 的库，且必须非零、不越界。v1 同一
位置仍为必须为零的 reserved 字段；旧 parser 不会把新格式解释为 v1。
startup 依赖图不得指向 online 库，全部依赖图仍有界且无环。所有对象在
启动前完成完整 SHA-256、XOS NOTE、真实 ELF、SONAME、DT_NEEDED 顺序和
跨对象版本匹配检查；缺失库也不能拖延到一次成功启动之后才发现。

同一只读 Files pin 同时用于身份验证、预检、转移和映射。启动时取得的
online approval pins 保留到进程退出；运行期不重新打开路径，不接受相邻
JSON、环境变量或目录搜索添加对象。路径被替换不会改变已批准实例。
`dlclose` 减少 GNU 引用；满足依赖和 TLS 析构留存规则后才解除映射及
namespace 占用，不声称返还 approval pin credit。最终进程退出才通过
Files 生命周期回收这些开放描述。

私有 GNU entry v4 在 pin plan 尾部新增四个 u32：`online_version`、
`online_mask`、`isolated_mask`、`online_reserved`。扩展关闭时字段全零，
保持 fixed-startup 语义；开启时 online_version 为 1，reserved 为零，
isolated_mask 是 online_mask 的子集。bootstrap 到 interpreter 的复制
必须保留这些字段，不能只复制旧版 pin 数组。

generation 至多 12 个对象，包括 bootstrap、interpreter、main 和启动库；
online spec 至多 8 个库，仍受这个总量限制。每个 online 对象预先预算
base 和 private 两个映射范围。private bias
比 base 增加 1 TiB；所有范围继续受既有地址、字节、对齐、可写重定位及
W^X/RELRO 检查。运行期使用两组各 16 个 lease，关闭后允许同一批准实例
再次装载，没有额外文件 authority；32 个内部 lease 槽不是 32 个可加载库。

## 公共调用与 namespace

| 项目 | 支持与拒绝边界 |
| --- | --- |
| 名称 | 只接纳批准的精确 SONAME；路径、空名称、`dlopen(NULL)` 和未批准对象拒绝 |
| Flags | `RTLD_NOW`、`RTLD_LOCAL`，以及显式 `RTLD_NOLOAD`；LAZY、GLOBAL、DEEPBIND、NODELETE 拒绝 |
| Base namespace | 支持批准库、依赖、GNU 引用计数、版本检查、构造和析构 |
| Private namespace | base 之外同时至多一个，ID 为 1；支持 NEWLM 创建和既有 ID，再开第二个拒绝 |
| Private 依赖 | 完整闭包必须无 TLS，且不能复制 libc、rtld 或线程运行库；不支持完整第二套 GNU 用户态 |
| 错误报告 | 准入拒绝不改变已有映射，并通过正常 GNU dlerror 捕获、读取和清除 |

`RTLD_NOLOAD` 的空结果只有在 `dlerror() == NULL` 时才用于证明该映射已
卸载；任意 loader 错误不能充当成功的卸载观测。GNU 的现有引用、依赖与
TLS destructor 留存规则仍决定何时可以真正解除映射。

在线入口记录拥有者 PID，并以实际 TID 串行化修改。另一个线程竞争产生
内部错误码 `EBUSY`，经 GNU dlerror 返回；公共 open 返回 NULL、close
返回 -1，不承诺 errno。同线程构造/析构递归最大深度为 8。准入、递归和
Files I/O 共用一个 5 秒绝对期限，不能在每次 I/O 或递归时重新计时；
该机制不对应用构造/析构函数建立强制执行超时，也不改变公共启动或 exec
使用的独立 generation 启动预算。

运行期 I/O 使用已经移交给 libc 的同一 Files 会话及其序号、串行化和
失败闩。未知结果不重放，也不重新使用 bootstrap 的早期会话序号。
VM 映射回滚或解除失败时，进程直接以 127 退出；此类失败不承诺通过
dlerror 返回后继续使用进程。
PID 改变不自动继承这项运行期在线权限；此 profile 的结果不能外推为
fork 后在线装卸组合已经通过。

## 动态 TLS 与工作线程退出

base namespace 只接纳不要求给既有线程补静态 TLS 的 online 对象。
允许实际 global-dynamic DTPMOD64/DTPOFF64 路径；拒绝 `DF_STATIC_TLS`、
TPOFF64（18）及 TLSDESC（36）。当前锁定 GNU 的 TLSDESC 实现可能尝试
静态 TLS 分配；native worker 没有加入 GNU 的 stack-list 注册机制，
所以不能仅凭 relocation 名称宣称它在运行期安全。startup 检查的既有
支持边界不因这一 online 限制改变。

online worker 使用 GNU 分配的可扩展 DTV。已经运行的 worker 在模块
加入后可以懒建立其独立 TLS；固定闭包原有的保留区 DTV 不进入这一
realloc/free 路径。C 夹具使用真实 `__cxa_thread_atexit_impl` 注册 TLS
析构，不借此宣称 C++ online library 已通过资格。

每个 native worker 占用一个退休记录，表内至多 4 项。线程运行完 TLS 析构后记录
最终 DTV；native thread-reaping 可以随后解除 TCB 映射。存活且不在退出
路径的 libc 线程使用专用 DTV 清理入口处理退休记录，不再次读取已被
回收的 TCB。创建或启动失败回滚其记录，join 路径也负责排空已退休项。
最后一个 worker 转入进程退出时保持自己的当前 TLS/DTV，供 GNU 进程
退出回调访问；不能在回调之前提前释放该上下文。

## 构建和资格边界

`build_glibc_shared_runtime.py --public-startup --online-libraries` 显式选择
此 profile，并把选择写入 native ABI 摘要。C SDK manifest 和完整树需要
独立给定的两个锚；GNU glibc/GCC 原始归档继续进行锁定签名验证。

`build_glibc_shared_gcc.py --public-runtime ... --unwinder-only` 为实际 C
pthread 退出组合构建匹配的 `libgcc_s`，其 manifest 绑定同一个 runtime；
该选项不产生完整 C++ SDK。`build_dynamic_program.py` 的
`--online-library-spec` 接收有序、显式的 C 库及其先行依赖，然后运行生产
ELF verifier 的完整离线预检。`build_dynamic_launcher.py` 只批准构建时
列出的二进制 generation。

runtime manifest 的 `public_runtime_built_not_run` 及其他构建 manifest 的
`built_not_run` 状态均保持原样。客体验证另外绑定 system
源码、native/C SDK、runtime/unwinder、应用、库和 controller 的实际字节，
运行前后均复核。报告分别记录 host/parser 检查与实际 guest 执行；旧失败
保留，新的 source 或 system 不借旧通过报告完成资格。

当前边界包括 C online libraries、单核虚拟机、base 加一个受限 private
namespace；不包含 C++ online DSO、任意系统库搜索、完整第二 libc、SMP、
物理硬件或与其他尚未合并 P1 profile 的完整组合资格。

## 2026-11-28 记录的目标资格

[完整证据](../reports/p1_k3_online_libraries_20261128/README.md) 绑定冻结源码
`86d39b31ade96ba7a609b9321e30ee63c0632441` 和 native system
`94674a7e28151485`。重新构建的 runtime manifest 为
`9c11b60d1c8b71471bb4a3ec7bd6546a6d1fd9d091497d34709327d52f89036d`，
独立重编并匹配它的 unwinder manifest 为
`83773c2bbb85f006f29562e76afaff1340a69a10dd76ee34823f0006590dd43d`。
它们保留原有 built-not-run 状态，独立 guest 报告提供执行结论。

七次冷启动的 16 项实际用例全部通过，每项都精确回到该次启动的
129790 free pages / 2 tasks / 0 completions。覆盖依赖/引用、namespace、
真实并发和已运行线程的动态 TLS、TLS 析构、最后 worker 的 GNU on_exit、
卸载循环、不可变 pin、默认拒绝，以及缺失/替换/错误版本对象和两种被拒绝
TLS relocation。Host 另有 6 组 mapping/worker 和 60 项 closure/verifier
检查，分别使用普通构建与 ASan/UBSan；未运行 LeakSanitizer。

该已执行 runtime 的 ABI domain 是 `xos-glibc-dynamic-capsule-v2`；这里的
generation v2 是另一项记录格式版本。后来的主线 catalog authority 和
capsule v3 需要匹配自己的构建与完整目标验收。源码集成、host 检查或相同
接口布局不会自动把本报告扩大为那个新组合的 guest 资格。
